# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Emit Result Envelope: one schema-checked emitter for every workflow.

A workflow with a headless contract ends each run, and each HARD HALT, with
one prefixed line that pipelines grep out of the workflow log:
`SKF_<NAME>_RESULT_JSON: {one-line JSON}`. The model never types that line.
It stages a payload file and runs this script, which fills the derived
fields, folds in the run's auto-decisions and warnings, checks the envelope
against the workflow's JSON Schema, writes the run's result files and
prints the line:

  uv run {helper} emit --workflow <name> --run-dir <run_dir> --result-dir <dir> < <run_dir>/result-context.json
  uv run {helper} emit-halt --workflow <name> --run-dir <run_dir> < <run_dir>/halt.json

Subcommands:

  emit       Build the envelope that ends a run from the context payload
             on stdin. Without --workflow it builds skf-setup's, from
             setup's own payload (see "skf-setup" below). Default
             subcommand.

  emit-halt  Build the envelope of a HARD HALT from the halt payload on
             stdin: {"phase", "reason", "halt_reason"?, "exit_code"?,
             "path"?, "status"?} plus any envelope field the halt already
             knows (a skill name, a version). Needs --workflow.

  emit-blocked
             skf-setup's halt: `emit-halt --workflow skf-setup` under its
             older name. Reads {"phase", "reason", "path"?} on stdin and
             emits a status 'blocked' envelope, with placeholders for the
             fields a halt does not know (tier 'Quick', no tools,
             config_path set to the path, files_written []).

  record     Append one entry to the run's sink: --decision reads one
             auto-decision (a JSON object) on stdin, --warning takes the
             warning text. With --workflow a decision is checked against
             that workflow's headless_decisions item schema first.

  validate   Read an envelope (without the prefix) as JSON on stdin and
             verify it against the workflow's schema (skf-setup's without
             --workflow). No stdout on success; non-zero exit + stderr
             error on failure. Useful for paranoid pipelines that want to
             validate a received envelope before consuming it.

  render-report
             skf-setup's interactive FORGE STATUS banner: reads the same
             payload as `emit` on stdin (plus the banner keys below),
             folds in the helper outputs --run-dir holds, and prints the
             banner's lines in English, one per line, ending with the
             REQUIRED TIER NOT MET block when --require-tier was not met.
             --tier-rules names skf-setup's references/tier-rules.md,
             which holds the tier descriptions and re-run messages
             (default: the copy beside this script's folder, in the source
             tree and in an installed project alike).

Workflow schemas. A workflow's envelope schema is
`schemas/skf-<name>-result-envelope.v<N>.json`, found beside this script in
both the source tree and an installed project. --workflow takes the
workflow's folder name (`skf-update-skill`) or the schema's stem
(`skf-update`); two versions of one schema resolve to the higher. The
schema tells the emitter what JSON Schema cannot in its `skf-envelope`
settings: a `$defs` entry that holds them as a `const` and that nothing
references. `$defs` and `const` are standard keywords, so a strict
validator (Ajv's default mode) still compiles the schema:

  "$defs": {"skf-envelope": {"const": {
    "workflow":          "skf-update-skill",
    "prefix":            "SKF_UPDATE_RESULT_JSON",
    "wrapper":           "skf_update" | null,
    "halt_status":       "blocked",
    "exit_codes":        {"<halt_reason>": <exit code>, ...},
    "success_exit_code": 0,
    "result_file":       "update-skill-result" | null
  }}}

  wrapper names the one property that wraps the envelope (null for a flat
  envelope); halt_status is the status a halt envelope carries unless its
  payload names one; exit_codes maps each halt_reason to its exit code, and
  success_exit_code is the code a null halt_reason carries (both optional);
  result_file is the stem of the run's result files (null: none).

Building an envelope (every workflow but skf-setup). Each payload key is an
envelope field of the same name, except `result_contract` and
`customization_resolver_unavailable` (below). Then:

  - A halt payload's phase, reason, halt_reason, exit_code, path and
    details become the fields of the same name the schema declares, and
    fill its `error` object: phase, reason, path and details by name,
    `code` from halt_reason, `message` from reason, and '<n/a>' for a
    required path the halt has none for. A key the schema has no place for
    is dropped. A payload that gives `error` itself keeps it whole.
  - exit_code, when the payload has none, is exit_codes[halt_reason], or
    for a finished run with a null halt_reason success_exit_code (else 0);
    a halt without a mapped halt_reason must give its exit_code. A status
    equal to halt_status needs a halt_reason and any other status a null
    one, and exit_code must match the mapping, when the schema declares
    them.
  - Stamped from the run, never typed: `timestamp` (ISO-8601 UTC, from the
    clock), `run_id` (the --run-dir folder name without its
    `<workflow>-` prefix) and `result_path` (the per-run result file this
    call wrote, or null), each when the schema declares it.
  - headless_decisions and warnings: the payload's own entries, then the
    sink's, duplicates dropped. A `customization_resolver_unavailable`
    reason becomes the warning `customization_resolver_unavailable:
    <reason>`. An optional list stays out of the envelope while empty.
  - A required field the payload leaves out gets its schema `default`,
    else null when the schema allows it; in a halt, else [], {}, false or
    0 by its type.

  The envelope's keys follow the schema's property order, and the line is
  ASCII JSON, non-ASCII text escaped, as skf-brief-skill's helper always
  printed it: no character in a value can break the line for a reader.

Run sink. Every run owns a folder, `_bmad-output/.skf-run/<workflow>-<run_id>/`,
passed as --run-dir. Each gate records its auto-decision there the moment
it decides, and each warning as it is raised, with `record`:

  {run_dir}/headless-decisions.jsonl   one decision object per line
  {run_dir}/warnings.jsonl             one warning string per line

so the decision trail survives context compaction and a halt reports the
decisions taken before it. `record` writes each line as ASCII JSON, so no
U+2028, U+2029 or U+0085 inside a value can split it for a reader that
breaks lines there, and the emitter splits the files on newlines alone. A
line that is not JSON (a write cut short) or a decision the schema rejects
is left out and named in the warnings (`sink_line_unreadable:
<file>:<line>`, `headless_decision_invalid: <file>:<line>: <error>`), so a
halt still emits.

Result files. With --result-dir naming a folder that exists (the version
folder), the call writes `<result_file>-<YYYYMMDD-HHmmss>.json` (UTC; `-2`,
`-3`, ... appended when a run already took that second's name) and then
the copy `<result_file>-latest.json`, each atomically. The file holds the
payload's `result_contract` object (see
`shared/references/output-contract-schema.md`) with `timestamp`, `run_id`,
`headless_decisions` and `warnings` stamped in, and the payload's own
`status` and `summary` where the contract leaves them out, or the envelope
itself when the payload has none. When --result-dir names no folder, nothing is
written: a halt before the version folder exists reports on stdout only.
A write that fails adds the warning `result_file_write_failed: <path>:
<reason>`, and a failed per-run record leaves `result_path` null. A
workflow whose `result_file` is null writes none: it ignores --result-dir
with the warning `result_dir_ignored: <workflow> writes no result file`.

Clock. The timestamp is the system clock's time, read with time.time().
The helper imports only argparse, json, os, pathlib, sys and time, all in
the standard library of every Python the halt contract may run it under,
so reading the clock needs no folder: a halt emits before any run folder
exists, and the call creates none.

skf-setup. setup keeps its own payload, which the emitter turns into the
envelope below (`emit` and `emit-blocked` keep working without --workflow).
Its envelope follows `schemas/skf-setup-result-envelope.v1.json` and prints
with sorted keys and raw UTF-8, except that U+2028, U+2029 and U+0085 are
escaped so the line stays one line. --run-dir appends the sink's warnings
that setup's own list does not already hold.

A setup run also stages each helper's JSON output in its run folder, as
the step that runs the helper writes it, so no step types those values
back into a payload:

  detect-tools.json    step 1, skf-detect-tools.py
  qmd-classify.json    step 3, skf-qmd-classify-collections.py
  clean-stale.json     step 3, skf-forge-tier-rw.py clean-stale

With --run-dir, `emit` and `render-report` fold them into the payload:
a staged output replaces the payload's own value of each field it is the
source of (fold_staged lists them). A file that holds no JSON object means
its helper failed (the classifier then reads as qmd unavailable); a file
that is absent means its step did not run the helper.

Context payload shape (consumed by `emit` for skf-setup):

  {
    "tier":                          "Quick|Forge|Forge+|Deep",
    "previous_tier":                 "Quick|Forge|Forge+|Deep|null",
    "tools":                         {"ast_grep": bool, "gh_cli": bool, "qmd": bool, "ccc": bool},
    "previous_tools":                {…same shape…|null},
    "config_path":                   "/abs/path/to/forge-tier.yaml",
    "ccc_index":                     {"status": "...", "indexed_path": "...|null", "file_count": int|null},
    "files_written":                 ["forge-tier.yaml", ...],
    "tier_override_active":          bool,
    "tier_override_invalid":         bool,
    "tier_override_invalid_value":   "string|null",
    "tier_override_invalid_suggestion": "string|null",
    "tier_override_unsafe":          bool,
    "tier_override_unsafe_missing":  ["gh", "qmd", ...],
    "require_tier_satisfied":        bool|null,
    "require_tier_failure_missing":  ["ccc", ...],
    "qmd_status":                    "absent|daemon_stopped|healthy",
    "tools_below_minimum":           [{"tool": "ast_grep", "name": "ast-grep", "version": "0.42.2",
                                       "minimum": "0.45.3", "upgrade": "string|null",
                                       "tier": "Forge|Forge+|Deep|null"}, ...],
    "ccc_exclusion_warnings":        ["string", ...],
    "ccc_registry_stale_removed":    ["/path", ...],
    "ccc_indexing_failed_reason":    "string|null",
    "orphan_auto_resolution":        null|{"action": "keep|remove", "count": int, "source": "headless-default|quiet-default|orphan-action-flag", "removed": ["name", ...], "failed": ["name", ...]},
    "customization_resolver_unavailable": "string|null",
    "error":                         null|{"phase","path","reason"}
  }

  The `tools` values may also be skf-detect-tools.py's own objects
  ({"available": bool, "version": ..., ...}), as detect-tools.json holds
  them. Without `files_written`, the emitter derives it: forge-tier.yaml,
  then preferences.yaml, settings.yml and ccc_index when
  `preferences_yaml_created`, `settings_yml_written` and a ccc_index
  status of "created" say so (none when `error` is set).

  When the step-3 orphan-removal gate is resolved non-interactively
  (headless or quiet default Keep, or an explicit --orphan-action), pass
  `orphan_auto_resolution` so the audit trail lands in `warnings`: most
  importantly when the destructive `remove` ran headlessly, which a
  pipeline otherwise could not distinguish from a no-op by reading the
  envelope alone. Its `removed` and `failed` lists name the collections
  the removal deleted and the ones it could not, and each becomes its own
  warning (`orphan_removed: <name>`, `orphan_remove_failed: <name>`).

  `tools_below_minimum` is skf-detect-tools.py's list of the tools below
  their minimum version, which detect-tools.json supplies. Each becomes the
  warning `tool_below_minimum: <name> <version> (minimum <minimum>)`, and
  the banner's Tool upgrades line; a tier tool among them already reads
  false under `tools`, so no envelope field changes.

  When the On Activation customization resolver was missing or failed,
  pass its one-line reason as `customization_resolver_unavailable`: the
  run then used only the skill's own customize.toml, and the warning tells
  a pipeline that the `_bmad/custom/` overrides were not applied. The
  emit-blocked payload takes the same key.

  The banner keys, which `render-report` reads (`emit` reads only the
  two it derives files_written from): "project_root" and
  "forge_data_folder" (resolved paths), "preferences_yaml_created",
  "settings_yml_written" and "gitignore_updated" (bool),
  "settings_yml_patterns_added" and "settings_yml_patterns_removed"
  (int), "hygiene_result" ("completed|qmd_unavailable|skipped"),
  "hygiene_healthy", "hygiene_orphaned_removed", "hygiene_orphaned_kept",
  "hygiene_stale_cleaned" and "ccc_registry_stale_cleaned" (int), and
  "require_tier" (the tier --require-tier named, or null). The staged
  helper outputs supply every hygiene key but the two orphan counts, and
  detect-tools.json supplies require_tier.

Caller does NOT need to compute warnings, tools_added/removed, or
tier_changed: the script derives them from the inputs above.

Setup's step 4 always passes `"error": null`: every halt that names a
phase emits through `emit-blocked` instead. A non-null error still
yields status 'blocked'.

CLI: the step files invoke it via `uv run`, like every sibling helper.
It imports only the standard library (dependencies = []) and must stay
that way: the setup halt contract runs `emit-blocked` for the On
Activation halts, which can fire before `uv` is proven present, under
the first of `uv run`, `python3`, `python` and `py -3` that works.

  echo '{...context payload...}' | uv run skf-emit-result-envelope.py emit
  uv run skf-emit-result-envelope.py emit --run-dir "{run_dir}" < "{run_dir}/report-context.json"
  uv run skf-emit-result-envelope.py render-report --run-dir "{run_dir}" --tier-rules "<skill>/references/tier-rules.md" < "{run_dir}/report-context.json"
  echo '{"phase":"...","reason":"...","path":"..."}' | uv run skf-emit-result-envelope.py emit-blocked
  echo '{"skf_setup":{...}}' | uv run skf-emit-result-envelope.py validate
  uv run skf-emit-result-envelope.py record --run-dir "{run_dir}" --warning "customization_resolver_unavailable: <reason>"

Exit codes:
  0 success
  1 user error (bad args, malformed JSON, validation failure)
  2 internal error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


ENVELOPE_PREFIX = "SKF_SETUP_RESULT_JSON: "
SCHEMA_FILE = Path(__file__).parent / "schemas" / "skf-setup-result-envelope.v1.json"
TOOL_KEYS = ("ast_grep", "gh_cli", "qmd", "ccc")
VALID_TIERS = ("Quick", "Forge", "Forge+", "Deep")
VALID_FILES = ("forge-tier.yaml", "preferences.yaml", "settings.yml", "ccc_index")
VALID_CCC_STATUS = ("fresh", "created", "failed", "none", "skipped")
# The helper outputs a skf-setup run stages in its run folder, each by the
# step that runs the helper; `emit` and `render-report` read them from
# --run-dir (see "skf-setup" in the module docstring).
STAGED_DETECT = "detect-tools.json"
STAGED_CLASSIFY = "qmd-classify.json"
STAGED_CLEAN_STALE = "clean-stale.json"
STAGED_FILES = (STAGED_DETECT, STAGED_CLASSIFY, STAGED_CLEAN_STALE)

SCHEMA_DIR = SCHEMA_FILE.parent
SETUP_WORKFLOW = "skf-setup"
# The `$defs` entry whose `const` holds a schema's emitter settings.
META_KEY = "skf-envelope"
META_FIELDS = ("workflow", "prefix", "wrapper", "halt_status", "exit_codes",
               "success_exit_code", "result_file")
SINK_DECISIONS = "headless-decisions.jsonl"
SINK_WARNINGS = "warnings.jsonl"
# The halt payload's own keys; each lands only where the schema has a place for it.
HALT_KEYS = ("phase", "reason", "halt_reason", "exit_code", "path", "details")
# Payload keys the emitter reads and never copies into the envelope.
PAYLOAD_ONLY_KEYS = ("result_contract", "customization_resolver_unavailable")
# The fields of a schema's `error` object a halt fills, and the halt key each reads.
ERROR_FIELDS = {"phase": "phase", "reason": "reason", "path": "path", "code": "halt_reason",
                "message": "reason", "halt_reason": "halt_reason", "exit_code": "exit_code",
                "details": "details"}
# The record fields a result_contract may leave out, taken from the payload's own.
CONTRACT_DEFAULTS = ("status", "summary")
# Every JSON Schema keyword _validate_against_schema enforces, and the ones
# it may skip: annotations, and `$defs`, which holds only the emitter's
# settings (no envelope schema has a `$ref`). An envelope schema uses no
# other keyword, so the built-in validator never passes what the schema
# forbids.
VALIDATOR_KEYWORDS = frozenset({"type", "enum", "const", "oneOf", "anyOf", "properties",
                                "additionalProperties", "required", "items", "uniqueItems",
                                "minLength", "minimum"})
ANNOTATION_KEYWORDS = frozenset({"$schema", "$id", "$defs", "title", "description", "default",
                                 "examples"})
# What str.splitlines() and some log readers break a line at, and json.dumps
# leaves raw when it keeps non-ASCII text (it escapes every control character).
RAW_LINE_BREAKS = ("\x85", "\u2028", "\u2029")
_MISSING = object()


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _read_stdin_json(label: str) -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        _die(1, f"{label}: empty stdin (expected JSON payload)")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        _die(1, f"{label}: invalid JSON on stdin: {e}")


# ─── derive helpers ─────────────────────────────────────────────────────────


def _normalize_tools(maybe_tools) -> dict:
    """Coerce either {key: bool} or {key: {available: bool}} into {key: bool}.

    skf-detect-tools.py emits the second shape; some callers will pass the
    first. Tolerate both for robustness; missing keys default to False.
    """
    if maybe_tools is None:
        return {k: False for k in TOOL_KEYS}
    out = {}
    for k in TOOL_KEYS:
        v = maybe_tools.get(k)
        if isinstance(v, dict):
            out[k] = bool(v.get("available", False))
        else:
            out[k] = bool(v)
    return out


def _compute_tool_deltas(current: dict, previous) -> tuple[list[str], list[str]]:
    """Return (added, removed) tool-key lists, sorted for determinism.

    First-run convention (previous is None or empty): added = currently
    available tools; removed = []. Matches the documented step 4 §4 rule.
    """
    cur = _normalize_tools(current)
    if not previous:
        added = sorted(k for k, v in cur.items() if v)
        return added, []
    prev = _normalize_tools(previous)
    added = sorted(k for k in TOOL_KEYS if cur[k] and not prev[k])
    removed = sorted(k for k in TOOL_KEYS if prev[k] and not cur[k])
    return added, removed


def _resolver_warning(payload: dict) -> list[str]:
    """The customization_resolver_unavailable warning, when the payload reports one.

    Every workflow's On Activation runs resolve_customization.py. When that
    script is missing or fails, the run falls back to the skill's own
    customize.toml, so the team and user overrides under `_bmad/custom/`
    silently do nothing; the payload key carries the resolver's reason so
    the envelope says so.
    """
    reason = payload.get("customization_resolver_unavailable")
    if not reason:
        return []
    text = reason.strip() if isinstance(reason, str) else ""
    return [f"customization_resolver_unavailable: {text or '<unknown>'}"]


def _assemble_warnings(payload: dict) -> list[str]:
    """Fold every documented warning source into the envelope's warnings array.

    Matches the field-rules block in step 4 §4 — pipelines should only need
    to consult `warnings` to surface non-fatal issues.
    """
    warnings: list[str] = _resolver_warning(payload)
    if payload.get("tier_override_invalid"):
        bad = payload.get("tier_override_invalid_value")
        suggestion = payload.get("tier_override_invalid_suggestion")
        bad_text = bad if bad is not None else "<unknown>"
        if suggestion:
            warnings.append(f"tier_override_invalid: {bad_text} (did you mean {suggestion}?)")
        else:
            warnings.append(f"tier_override_invalid: {bad_text}")
    if payload.get("tier_override_unsafe"):
        missing = payload.get("tier_override_unsafe_missing", []) or []
        warnings.append(f"tier_override_unsafe: missing {', '.join(missing) if missing else '<none>'}")
    for w in payload.get("ccc_exclusion_warnings", []) or []:
        warnings.append(str(w))
    for p in payload.get("ccc_registry_stale_removed", []) or []:
        warnings.append(f"ccc_registry_stale_removed: {p}")
    if payload.get("qmd_status") == "daemon_stopped":
        warnings.append("qmd_daemon_stopped")
    for tool in _objects(payload.get("tools_below_minimum")):
        warnings.append(f"tool_below_minimum: {_tool_name(tool)} {tool.get('version')} "
                        f"(minimum {tool.get('minimum')})")
    failure_reason = payload.get("ccc_indexing_failed_reason")
    if failure_reason:
        warnings.append(f"ccc_indexing_failed: {failure_reason}")
    if payload.get("require_tier_satisfied") is False:
        missing = payload.get("require_tier_failure_missing", []) or []
        warnings.append(
            f"require_tier_failed: missing {', '.join(missing) if missing else '<none>'}"
        )
    orphan = payload.get("orphan_auto_resolution")
    if isinstance(orphan, dict) and orphan.get("action"):
        action = str(orphan.get("action"))
        count = orphan.get("count", 0)
        source = str(orphan.get("source", "headless-default"))
        warnings.append(
            f"orphan_auto_resolution: {action} {count} orphaned collection(s) "
            f"(non-interactive, {source})"
        )
        # A removal nobody confirmed names each collection it deleted, and
        # each it could not, so the audit trail says what to rebuild.
        warnings += [f"orphan_removed: {name}" for name in _strings(orphan.get("removed"))]
        warnings += [f"orphan_remove_failed: {name}" for name in _strings(orphan.get("failed"))]
    return warnings


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _strings(value) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _objects(value) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _tool_name(tool: dict) -> str:
    """A tools_below_minimum entry's name, as the docs write it."""
    return str(tool.get("name") or tool.get("tool"))


def _normalize_files_written(maybe_files) -> list[str]:
    """Accept either a list of names or a dict {name: bool}; emit sorted-canonical list."""
    if maybe_files is None:
        return []
    if isinstance(maybe_files, dict):
        names = [k for k, v in maybe_files.items() if v]
    elif isinstance(maybe_files, list):
        names = [str(x) for x in maybe_files]
    else:
        _die(1, f"files_written must be list or dict, got {type(maybe_files).__name__}")
    # Filter to documented names only; preserve canonical order rather than
    # caller-provided order so two callers with the same files get byte-identical
    # output.
    return [name for name in VALID_FILES if name in names]


def _files_written(payload: dict, error) -> list[str]:
    """files_written as the payload gives it, else derived from the run's flags.

    A finished run always wrote forge-tier.yaml; preferences.yaml,
    settings.yml and the ccc index count when preferences_yaml_created,
    settings_yml_written and a ccc_index status of "created" say so. An
    envelope with an error reports no file.
    """
    if "files_written" in payload:
        return _normalize_files_written(payload["files_written"])
    if error is not None:
        return []
    return _normalize_files_written({
        "forge-tier.yaml": True,
        "preferences.yaml": payload.get("preferences_yaml_created") is True,
        "settings.yml": payload.get("settings_yml_written") is True,
        "ccc_index": _dict(payload.get("ccc_index")).get("status") == "created",
    })


def _normalize_ccc_index(maybe_idx) -> dict:
    """Coerce caller's ccc_index dict to the envelope shape (drops extras)."""
    if maybe_idx is None:
        return {"status": "none", "indexed_path": None, "file_count": None}
    return {
        "status": maybe_idx.get("status", "none"),
        "indexed_path": maybe_idx.get("indexed_path"),
        "file_count": maybe_idx.get("file_count"),
    }


def _normalize_error(maybe_error) -> dict | None:
    if maybe_error is None:
        return None
    if not isinstance(maybe_error, dict):
        _die(1, f"error must be null or object, got {type(maybe_error).__name__}")
    required = {"phase", "path", "reason"}
    missing = required - set(maybe_error.keys())
    if missing:
        _die(1, f"error object missing required keys: {sorted(missing)}")
    return {
        "phase":  str(maybe_error["phase"]),
        "path":   str(maybe_error["path"]),
        "reason": str(maybe_error["reason"]),
    }


# ─── envelope assembly ──────────────────────────────────────────────────────


def assemble_envelope(payload: dict) -> dict:
    """Build the canonical envelope from a context payload. Pure function."""
    tier = payload.get("tier")
    if tier not in VALID_TIERS:
        _die(1, f"tier must be one of {VALID_TIERS}, got {tier!r}")

    previous_tier = payload.get("previous_tier")
    if previous_tier is not None and previous_tier not in VALID_TIERS:
        _die(1, f"previous_tier must be one of {VALID_TIERS} or null, got {previous_tier!r}")
    tier_changed = previous_tier is not None and previous_tier != tier

    tools = _normalize_tools(payload.get("tools"))
    tools_added, tools_removed = _compute_tool_deltas(
        payload.get("tools"), payload.get("previous_tools")
    )

    config_path = payload.get("config_path")
    if not isinstance(config_path, str) or not config_path:
        _die(1, "config_path must be a non-empty string")

    ccc_index = _normalize_ccc_index(payload.get("ccc_index"))
    if ccc_index["status"] not in VALID_CCC_STATUS:
        _die(1, f"ccc_index.status must be one of {VALID_CCC_STATUS}, got {ccc_index['status']!r}")

    require_tier_satisfied = payload.get("require_tier_satisfied")
    if require_tier_satisfied is not None and not isinstance(require_tier_satisfied, bool):
        _die(1, f"require_tier_satisfied must be bool or null, got {type(require_tier_satisfied).__name__}")

    error = _normalize_error(payload.get("error"))
    status = _compute_status(error, require_tier_satisfied)

    return {
        "skf_setup": {
            "status": status,
            "tier": tier,
            "previous_tier": previous_tier,
            "tier_changed": tier_changed,
            "tools": tools,
            "tools_added": tools_added,
            "tools_removed": tools_removed,
            "config_path": config_path,
            "ccc_index": ccc_index,
            "files_written": _files_written(payload, error),
            "tier_override_active": bool(payload.get("tier_override_active", False)),
            "tier_override_invalid": bool(payload.get("tier_override_invalid", False)),
            "require_tier_satisfied": require_tier_satisfied,
            "warnings": _assemble_warnings(payload),
            "error": error,
        }
    }


def _compute_status(error: dict | None, require_tier_satisfied) -> str:
    """Derive the single-field status from error + require_tier_satisfied.

    - 'blocked'      when error is non-null: a halt produced the envelope,
                     and error.phase names it (a write failure is
                     'step 2:write-tools', 'step 2:init-prefs' or
                     'step 2:forge-data-dir')
    - 'tier_failure' when require_tier_satisfied is False
    - 'success'      otherwise

    Both envelope builders derive status here, so every value it returns
    is one the schema's status enum lists.
    """
    if error is not None:
        return "blocked"
    if require_tier_satisfied is False:
        return "tier_failure"
    return "success"


def emit_envelope_line(envelope: dict) -> str:
    """Serialize the envelope as one prefixed line. No embedded newlines, sort_keys=True for determinism.

    The body keeps non-ASCII text raw, except the RAW_LINE_BREAKS, which only
    a string can hold and which are escaped there so the line stays one line.
    """
    body = json.dumps(envelope, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    for char in RAW_LINE_BREAKS:
        body = body.replace(char, f"\\u{ord(char):04x}")
    if "\n" in body:
        _die(2, "envelope serialization produced embedded newline (should be impossible)")
    return ENVELOPE_PREFIX + body


# ─── skf-setup: staged helper outputs ───────────────────────────────────────


def read_staged(run_dir: Path | None) -> dict:
    """The helper outputs a setup run staged in its run folder, by file name.

    Each value is the helper's JSON object, or None when the file holds
    none: the helper exited non-zero, so its redirected stdout stayed
    empty. A file that is absent is left out, because its step never ran
    the helper (step 3 runs none below Deep tier without ccc).
    """
    staged: dict = {}
    if run_dir is None:
        return staged
    for name in STAGED_FILES:
        try:
            # utf-8-sig: a shell that writes a byte-order mark still stages JSON.
            text = (run_dir / name).read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            text = ""
        try:
            value = json.loads(text) if text.strip() else None
        except json.JSONDecodeError:
            value = None
        staged[name] = value if isinstance(value, dict) else None
    return staged


def fold_staged(payload: dict, staged: dict) -> dict:
    """The setup payload with the fields each staged helper output is the source of.

    A staged output replaces the payload's own value of every field it
    holds: the step files no longer type those values, so the helper's are
    the ones that count.

      detect-tools.json   tier, previous_tier, tools, previous_tools, the
                          tier_override_* and require_tier* fields,
                          qmd_status and tools_below_minimum
      qmd-classify.json   hygiene_result ("completed", or "qmd_unavailable"
                          when the classifier failed) and hygiene_healthy
      clean-stale.json    hygiene_stale_cleaned, ccc_registry_stale_cleaned
                          and ccc_registry_stale_removed (none when it failed)
    """
    out = dict(payload)
    detect = staged.get(STAGED_DETECT)
    if detect is not None:
        tier, prior = _dict(detect.get("tier")), _dict(detect.get("prior"))
        required, tools = _dict(detect.get("require_tier")), _dict(detect.get("tools"))
        out.update({
            "tier": tier.get("calculated"),
            "previous_tier": prior.get("previous_tier"),
            "tools": tools,
            "previous_tools": prior.get("previous_tools") or None,
            "tier_override_active": tier.get("override_applied") is True,
            "tier_override_invalid": tier.get("override_invalid") is True,
            "tier_override_invalid_value": tier.get("override_invalid_value"),
            "tier_override_invalid_suggestion": tier.get("override_invalid_suggestion"),
            "tier_override_unsafe": tier.get("override_unsafe") is True,
            "tier_override_unsafe_missing": _strings(tier.get("override_unsafe_missing")),
            "require_tier": required.get("requested"),
            "require_tier_satisfied": required.get("satisfied"),
            "require_tier_failure_missing": _strings(required.get("missing_tools")),
            "qmd_status": _dict(tools.get("qmd")).get("status"),
            "tools_below_minimum": _objects(detect.get("tools_below_minimum")),
        })
    if STAGED_CLASSIFY in staged:
        healthy = _dict(staged[STAGED_CLASSIFY]).get("healthy")
        completed = isinstance(healthy, list)
        out["hygiene_result"] = "completed" if completed else "qmd_unavailable"
        out["hygiene_healthy"] = len(healthy) if completed else 0
    if STAGED_CLEAN_STALE in staged:
        cleaned = _dict(staged[STAGED_CLEAN_STALE])
        pruned = _strings(cleaned.get("ccc_removed"))
        out["hygiene_stale_cleaned"] = len(_strings(cleaned.get("qmd_removed")))
        out["ccc_registry_stale_cleaned"] = len(pruned)
        out["ccc_registry_stale_removed"] = pruned
    return out


# ─── skf-setup: FORGE STATUS banner ─────────────────────────────────────────


BANNER_RULE = "═" * 39
# The name the banner gives each tool key.
TOOL_NAMES = {"ast_grep": "ast-grep", "gh_cli": "gh", "qmd": "qmd", "ccc": "ccc"}
# tier-rules.md sits beside this script's folder in the source tree
# (src/skf-setup/) and in an installed project (_bmad/skf/skf-setup/).
TIER_RULES_FILE = Path(__file__).resolve().parent.parent.parent / "skf-setup" / "references" / "tier-rules.md"
# Each tier-rules.md heading the banner reads, and the key its copy goes under.
TIER_RULES_HEADINGS = {"Quick Tier": "Quick", "Forge Tier": "Forge", "Forge+ Tier": "Forge+",
                       "Deep Tier": "Deep", "Upgrade": "upgrade", "Downgrade": "downgrade",
                       "Same": "same"}
NEXT_STEPS = (
    "  Next: the fastest start is `@Ferris forge-auto <repo-or-doc-url>`: one command auto-scopes, "
    "briefs, compiles, tests at a 90% quality gate, and exports a verified skill with zero "
    "configuration. Prefer to scope by hand? `/skf-brief-skill` scopes your first compilation "
    "target, or `/skf-quick-skill` is a fast template-driven path. Already have a skill? "
    "`/skf-audit-skill` drift-checks an existing skill against current sources."
)


def load_tier_rules(path: Path) -> dict:
    """The tier descriptions and re-run messages of tier-rules.md, by key.

    Each is the first non-blank line under its `### <heading>`, without its
    surrounding double quotes, so the banner's tier wording lives in that
    one file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        _die(1, f"render-report: cannot read the tier copy {path.as_posix()}: {e}")
    copy: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            key = TIER_RULES_HEADINGS.get(stripped[4:].strip()) if stripped.startswith("### ") else None
        elif key and stripped:
            if len(stripped) > 1 and stripped[0] == stripped[-1] == '"':
                stripped = stripped[1:-1]
            copy.setdefault(key, stripped)
            key = None
    missing = [heading for heading, name in TIER_RULES_HEADINGS.items() if name not in copy]
    if missing:
        _die(1, f"render-report: {path.as_posix()} has no copy under: {', '.join(missing)}")
    return copy


def _count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _names(keys) -> str:
    return ", ".join(TOOL_NAMES.get(key, key) for key in keys)


def _tool_line(key: str, probe, ccc_daemon) -> str:
    """One Tools Detected line: the tool and its version, the probe's version
    line without the tool's name or a leading "version" (gh prints
    `gh version 2.91.0 (...)`). ccc also shows its daemon; its version is the
    one `uv tool list` gave, when uv installed it."""
    name = TOOL_NAMES[key]
    version = str(_dict(probe).get("version") or "").strip()
    for word in (name, "version"):
        if version.lower().startswith(word + " "):
            version = version[len(word) + 1:].lstrip()
    line = f"  - {name} {version}" if version else f"  - {name}"
    return f"{line} (daemon {ccc_daemon})" if key == "ccc" and ccc_daemon else line


def _upgrade_line(tool: dict) -> str:
    """One Tool upgrades line: the version found, the minimum, how to upgrade
    and, for a tier tool, the tier it counts toward once upgraded."""
    line = f"- Upgrade {_tool_name(tool)} {tool.get('version')} to {tool.get('minimum')} or newer"
    if tool.get("upgrade"):
        line += f" ({tool['upgrade']})"
    return line + (f" to use the {tool['tier']} tier" if tool.get("tier") else "")


def _tier_change_message(copy: dict, previous: str, current: str, added, removed) -> str:
    """tier-rules.md's upgrade or downgrade message, filled in.

    With no tool to name (a tier_override moved the tier), the message
    stops after its first sentence.
    """
    upgrade = VALID_TIERS.index(current) > VALID_TIERS.index(previous)
    message = copy["upgrade" if upgrade else "downgrade"]
    if not (added if upgrade else removed):
        head, sep, _ = message.partition("{current}.")
        message = head + sep
    return (message.replace("{previous}", previous).replace("{current}", current)
            .replace("{newly available tool(s)}", _names(added)).replace("{tool}", _names(removed)))


def render_report(payload: dict, copy: dict) -> list[str]:
    """The FORGE STATUS banner of a finished setup run, one string per line.

    Each `{if ...}` condition of the banner template is one test below, on
    the payload (with the staged helper outputs folded in) and the envelope
    fields derived from it; the tests keep the template. The lines are
    English; the step translates them.
    """
    inner = assemble_envelope(payload)["skf_setup"]
    tier, previous, tools = inner["tier"], inner["previous_tier"], inner["tools"]
    added, removed, changed = inner["tools_added"], inner["tools_removed"], inner["tier_changed"]
    index = inner["ccc_index"]["status"]
    probes = _dict(payload.get("tools"))
    ccc_daemon = _dict(probes.get("ccc")).get("daemon")
    root = str(payload.get("project_root") or "{project-root}").rstrip("/\\")
    hygiene = payload.get("hygiene_result")
    prefs_created = payload.get("preferences_yaml_created")
    settings_written = payload.get("settings_yml_written")
    # A tool below its minimum is installed: its Tool upgrades line replaces
    # an install hint, and it is never called "no longer detected".
    below = _objects(payload.get("tools_below_minimum"))
    below_keys = {str(tool.get("tool")) for tool in below}
    removed_shown = [key for key in removed if key not in below_keys]

    blocks = [[BANNER_RULE, "  FORGE STATUS", BANNER_RULE], [f"  Tier:  {tier}", f"  {copy[tier]}"]]

    detected = ["  Tools Detected:"]
    detected += [_tool_line(key, probes.get(key), ccc_daemon) for key in TOOL_KEYS if tools[key]]
    if not any(tools.values()):
        # With no tool counted, the only climb hint is ast-grep's install line.
        section = "Tool upgrades" if "ast_grep" in below_keys else "Climb to next tier"
        detected.append(f'  (none yet, see "{section}" below)')
    blocks.append(detected)

    if below:
        blocks.append(["  Tool upgrades:"] + [f"  {_upgrade_line(tool)}" for tool in below])

    if tier != "Deep":
        ast_grep, qmd_status = tools["ast_grep"], payload.get("qmd_status")
        hints = [hint for holds, hint in (
            (not ast_grep and "ast_grep" not in below_keys,
             "- Install ast-grep (https://ast-grep.github.io): unlocks AST-backed code analysis (Forge tier)"),
            (ast_grep and not tools["ccc"] and "ccc" not in below_keys,
             "- Install cocoindex-code (https://github.com/cocoindex-io/cocoindex-code): adds "
             "semantic-guided precision compilation (Forge+ tier)"),
            (ast_grep and not tools["gh_cli"] and "gh_cli" not in below_keys,
             "- Install GitHub CLI (https://cli.github.com): required for Deep tier "
             "(cross-repository synthesis)"),
            (ast_grep and not tools["qmd"] and qmd_status == "absent",
             "- Install qmd (https://github.com/tobi/qmd): required for Deep tier (knowledge search)"),
            (ast_grep and not tools["qmd"] and qmd_status == "daemon_stopped" and "qmd" not in below_keys,
             "- Start the qmd daemon (already installed): run `qmd start` (or your distribution's "
             "qmd service command) to unlock Deep tier (knowledge search)"),
            (tools["ccc"] and ccc_daemon == "error",
             "- The ccc daemon is reporting errors: run `ccc doctor` to diagnose. CCC index will "
             "fail until resolved"),
        ) if holds]
        if hints:
            blocks.append(["  Climb to next tier:"] + [f"  {hint}" for hint in hints])

    if hygiene == "completed":
        qmd = ["  QMD Registry:", f"  {_count(payload.get('hygiene_healthy'))} collection(s) healthy"]
        for key, what in (("hygiene_orphaned_removed", "orphaned collection(s) removed"),
                          ("hygiene_orphaned_kept", "orphaned collection(s) kept"),
                          ("hygiene_stale_cleaned", "stale QMD registry entry/entries cleaned")):
            if _count(payload.get(key)) > 0:
                qmd.append(f"  {_count(payload.get(key))} {what}")
        blocks.append(qmd)
    if _count(payload.get("ccc_registry_stale_cleaned")) > 0:
        blocks.append([f"  CCC Registry: {_count(payload.get('ccc_registry_stale_cleaned'))} stale "
                       "entry/entries cleaned"])
    if hygiene == "completed" and _count(payload.get("hygiene_healthy")) == 0:
        blocks.append(["  QMD Registry: empty. Collections are created automatically when you run "
                       "/skf-create-skill."])
    if hygiene == "qmd_unavailable":
        blocks.append(["  QMD Registry: skipped (qmd unavailable; if the daemon is stopped, "
                       "`qmd start` restores it)."])

    if tools["ccc"]:
        ccc = ["  CCC Index:"]
        # A failed `ccc index` can report on several lines; its line stays one line.
        reason = " ".join(str(payload.get("ccc_indexing_failed_reason") or "").split())
        ccc += [f"  {line}" for status, line in (
            ("fresh", "up to date, semantic discovery ready"),
            ("created", "indexed this run, semantic discovery ready"),
            ("skipped", "skipped (--ccc-skip-index). Run `/skf-setup` without --ccc-skip-index to "
                        "build or refresh the index when you're ready"),
            ("failed", "indexing failed, semantic discovery unavailable this session"
                       + (f" ({reason})" if reason else "")),
        ) if index == status]
        notes = _strings(payload.get("ccc_exclusion_warnings"))
        if notes:
            # A note that names the project root in SKF's words writes the
            # placeholder, shown here as the resolved root; the envelope keeps it.
            ccc.append("  CCC exclusion notes:")
            ccc += [f"  - {note.replace('{project-root}', root)}" for note in notes]
        blocks.append(ccc)

    config_path = inner["config_path"]
    cut = max(config_path.rfind("/"), config_path.rfind("\\")) + 1
    forge_data = str(payload.get("forge_data_folder") or "{forge_data_folder}").rstrip("/\\")
    files = ["  Files written this run:", f"  - forge-tier.yaml: {config_path}"]
    if prefs_created is True:
        files.append(f"  - preferences.yaml: {config_path[:cut]}preferences.yaml (first-run defaults)")
    files.append(f"  - {forge_data}/ (directory ensured)")
    if settings_written is True:
        pruned = _count(payload.get("settings_yml_patterns_removed"))
        files.append(f"  - .cocoindex_code/settings.yml: {root}/.cocoindex_code/settings.yml "
                     f"({_count(payload.get('settings_yml_patterns_added'))} SKF exclusion pattern(s) merged"
                     + (f", {pruned} stale SKF pattern(s) removed" if pruned > 0 else "") + ")")
    if payload.get("gitignore_updated") is True:
        files.append(f"  - .gitignore: {root}/.gitignore (`/.cocoindex_code/` added by `ccc init`)")
    if index == "created":
        count = inner["ccc_index"]["file_count"]
        files.append("  - .cocoindex_code/ ccc index" + (f": {count} files indexed" if count is not None else ""))
    blocks.append(files)

    if inner["tier_override_active"]:
        blocks.append(["  Note: Tier override active (set in preferences.yaml)"])
    if inner["tier_override_invalid"]:
        suggestion = payload.get("tier_override_invalid_suggestion")
        blocks.append([
            f'  Note: tier_override value "{payload.get("tier_override_invalid_value")}" in '
            "preferences.yaml is not valid.",
            *([f'        Did you mean "{suggestion}"?'] if suggestion is not None else []),
            "        Valid values are case-sensitive: Quick, Forge, Forge+, Deep. "
            f"Using detected tier {tier}.",
        ])
    if payload.get("tier_override_unsafe") is True:
        missing = ", ".join(_strings(payload.get("tier_override_unsafe_missing")))
        blocks.append([
            f"  Warning: tier_override is forcing {tier} but the underlying tool prerequisites are "
            "not satisfied.",
            f"           Missing: {missing}. The override is honored, but downstream skills that",
            "           rely on the missing tool(s) will fail at runtime. Install the missing tool(s) "
            "or remove",
            "           the override from preferences.yaml.",
        ])

    if previous is None:
        blocks.append([f"  Initial detection: {tier} tier established."])
    if changed:
        blocks.append([f"  {_tier_change_message(copy, previous, tier, added, removed_shown)}"])
    if not changed and not added and not removed and previous is not None:
        same = [f"  {copy['same'].replace('{current}', tier)}"]
        if prefs_created is False and settings_written is False and index == "fresh":
            same.append("  Your preferences and ccc settings were left untouched, and the ccc index "
                        "was already current.")
        if prefs_created is False and settings_written is False and index == "skipped":
            same.append("  Your preferences and ccc settings were left untouched; the ccc index was "
                        "not checked (--ccc-skip-index).")
        if prefs_created is False and index == "none":
            same.append("  Your preferences were left untouched.")
        blocks.append(same)
    if not changed and (added or removed) and previous is not None:
        delta = [f"  Tier unchanged: {tier}."]
        if added:
            deep_ccc = " ccc enhances Deep tier transparently." if "ccc" in added and tier == "Deep" else ""
            delta.append(f"  Newly detected: {_names(added)}.{deep_ccc}")
        if removed_shown:
            delta.append(f"  No longer detected: {_names(removed_shown)}. Re-install to restore those capabilities.")
        blocks.append(delta)

    blocks += [[BANNER_RULE, f"  Forge ready. {tier} tier active.", BANNER_RULE], [NEXT_STEPS]]
    if inner["require_tier_satisfied"] is False:
        missing = ", ".join(_strings(payload.get("require_tier_failure_missing"))) or "<none>"
        blocks += [[BANNER_RULE, "  REQUIRED TIER NOT MET", BANNER_RULE],
                   [f"  Required:  {payload.get('require_tier') or '<unknown>'}", f"  Detected:  {tier}",
                    f"  Missing:   {missing}"],
                   ["  Install or upgrade the missing tool(s) and re-run, or relax `--require-tier`.", BANNER_RULE]]
    lines: list[str] = []
    for block in blocks:
        lines += ([""] if lines else []) + block
    return lines


# ─── minimal stdlib JSON Schema validator ───────────────────────────────────


def _load_schema() -> dict:
    if not SCHEMA_FILE.exists():
        _die(2, f"schema file missing: {SCHEMA_FILE}")
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _validate_against_schema(value, schema: dict, path: str = "$") -> list[str]:
    """Return a list of error strings (empty = valid).

    Implements only the subset of Draft 2020-12 features the envelope
    schemas use, the VALIDATOR_KEYWORDS: type, enum, const, oneOf, anyOf,
    properties, additionalProperties, required, items, uniqueItems,
    minLength, minimum. Sufficient to catch every violation those schemas
    can express; not a general-purpose validator.
    """
    errors: list[str] = []

    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not _validate_against_schema(value, sub, path))
        if matches != 1:
            errors.append(f"{path}: matched {matches} of {len(schema['oneOf'])} oneOf branches (expected exactly 1)")
        return errors

    if "anyOf" in schema:
        if all(_validate_against_schema(value, sub, path) for sub in schema["anyOf"]):
            errors.append(f"{path}: matched none of {len(schema['anyOf'])} anyOf branches")
        return errors

    expected_type = schema.get("type")
    if expected_type is not None:
        if not _matches_type(value, expected_type):
            errors.append(f"{path}: expected type {expected_type}, got {type(value).__name__}")
            return errors

    if "enum" in schema:
        if value not in schema["enum"]:
            errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value {value!r} is not {schema['const']!r}")

    if isinstance(value, dict):
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        present = set(value.keys())
        missing = required - present
        for k in sorted(missing):
            errors.append(f"{path}: missing required property {k!r}")
        if schema.get("additionalProperties") is False:
            extra = present - set(props.keys())
            for k in sorted(extra):
                errors.append(f"{path}: unexpected property {k!r}")
        for k, sub in props.items():
            if k in value:
                errors.extend(_validate_against_schema(value[k], sub, f"{path}.{k}"))

    if isinstance(value, list):
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(_validate_against_schema(item, schema["items"], f"{path}[{i}]"))
        if schema.get("uniqueItems") and len(value) != len(set(map(_freeze, value))):
            errors.append(f"{path}: items not unique")

    if isinstance(value, str) and "minLength" in schema:
        if len(value) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema:
        if value < schema["minimum"]:
            errors.append(f"{path}: value {value} below minimum {schema['minimum']}")

    return errors


def _matches_type(value, expected) -> bool:
    """Implement JSON Schema 'type' for a single string OR a list of allowed types."""
    if isinstance(expected, list):
        return any(_matches_type(value, t) for t in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _freeze(v):
    """Make a value hashable for uniqueItems checks."""
    if isinstance(v, dict):
        return tuple(sorted((k, _freeze(val)) for k, val in v.items()))
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


# ─── workflow schemas ───────────────────────────────────────────────────────


def _schema_version(path: Path, suffix: str = "-result-envelope.v") -> tuple[str, int] | None:
    """(stem, version) of an envelope schema file name, or None for another file."""
    stem, sep, version = path.name[: -len(".json")].rpartition(suffix)
    if not sep or not version.isdigit():
        return None
    return stem, int(version)


def _read_schema(path: Path) -> dict | None:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return schema if isinstance(schema, dict) else None


def load_workflow_schema(workflow: str) -> tuple[dict, Path]:
    """Return (schema, path) of the newest envelope schema of `workflow`.

    A schema belongs to the workflow its settings name (`skf-update-skill`),
    and answers to its file stem too (`skf-update` for
    skf-update-result-envelope.v1.json). The stem is tried first, so an
    unreadable sibling schema never stops another workflow's halt.
    """
    candidates = sorted(SCHEMA_DIR.glob(f"{workflow}-result-envelope.v*.json"))
    found = []
    for path in candidates:
        parsed = _schema_version(path)
        if parsed is None or parsed[0] != workflow:
            continue
        schema = _read_schema(path)
        if schema is None:
            _die(2, f"schema file unreadable: {path.name}")
        found.append((parsed[1], schema, path))
    if not found:
        for path in sorted(SCHEMA_DIR.glob("*-result-envelope.v*.json")):
            parsed = _schema_version(path)
            schema = _read_schema(path) if parsed else None
            meta = _meta_of(schema)
            if meta is not None and meta.get("workflow") == workflow:
                found.append((parsed[1], schema, path))
    if not found:
        _die(1, f"no result-envelope schema for workflow {workflow!r} in {SCHEMA_DIR.as_posix()}")
    _, schema, path = max(found, key=lambda item: item[0])
    _meta(schema, path)
    return schema, path


def _meta_of(schema) -> dict | None:
    """A schema's emitter settings, the `const` of its `$defs` entry META_KEY, or None."""
    defs = schema.get("$defs") if isinstance(schema, dict) else None
    entry = defs.get(META_KEY) if isinstance(defs, dict) else None
    meta = entry.get("const") if isinstance(entry, dict) else None
    return meta if isinstance(meta, dict) else None


def _meta(schema: dict, path: Path | None = None) -> dict:
    """The schema's emitter settings, checked for the fields the emitter needs."""
    meta = _meta_of(schema)
    name = path.name if path else "schema"
    if meta is None:
        _die(2, f"{name}: no $defs.{META_KEY}.const object")
    for key in ("workflow", "prefix"):
        if not isinstance(meta.get(key), str) or not meta[key]:
            _die(2, f"{name}: {META_KEY}.{key} must be a non-empty string")
    wrapper = meta.get("wrapper")
    if wrapper is not None and not isinstance(schema.get("properties", {}).get(wrapper), dict):
        _die(2, f"{name}: {META_KEY}.wrapper {wrapper!r} is not a property of the schema")
    return meta


def _inner_schema(schema: dict) -> dict:
    """The schema of the envelope's fields: under the wrapper, or the whole schema."""
    wrapper = (_meta_of(schema) or {}).get("wrapper")
    return schema["properties"][wrapper] if wrapper else schema


def _allows(prop: dict, type_name: str) -> bool:
    """True when the property schema accepts a value of JSON type `type_name`."""
    branches = prop.get("oneOf") or prop.get("anyOf")
    if branches:
        return any(_allows(branch, type_name) for branch in branches)
    declared = prop.get("type")
    if isinstance(declared, list):
        return type_name in declared
    return declared == type_name


def _object_branch(prop: dict) -> dict | None:
    """The object schema of a property that may also be null (`error`)."""
    if prop.get("type") == "object" or "properties" in prop:
        return prop
    for branch in prop.get("oneOf") or prop.get("anyOf") or []:
        if isinstance(branch, dict) and branch.get("type") == "object":
            return branch
    return None


def _placeholder(prop: dict, halt: bool):
    """The value a required field the payload left out takes, or _MISSING.

    The schema's `default` first, then null where the schema allows it. A
    halt knows little about its run, so it also takes an empty list, false
    or 0 by type; a finished run must supply those itself.
    """
    if "default" in prop:
        return json.loads(json.dumps(prop["default"]))
    if _allows(prop, "null"):
        return None
    if halt:
        if _allows(prop, "array"):
            return []
        if _allows(prop, "boolean"):
            return False
        if _allows(prop, "integer") or _allows(prop, "number"):
            return 0
        if _allows(prop, "object") and not prop.get("required"):
            return {}
    return _MISSING


def _ordered(value, schema):
    """Order an object's keys as its schema lists them (unknown keys last)."""
    if isinstance(value, dict) and isinstance(schema, dict):
        branch = _object_branch(schema) or schema
        props = branch.get("properties") or {}
        keys = [k for k in props if k in value] + [k for k in value if k not in props]
        return {k: _ordered(value[k], props.get(k, {})) for k in keys}
    if isinstance(value, list) and isinstance(schema, dict) and isinstance(schema.get("items"), dict):
        return [_ordered(item, schema["items"]) for item in value]
    return value


# ─── run sink ───────────────────────────────────────────────────────────────


def read_sink(run_dir: Path | None) -> tuple[list[tuple[str, dict]], list[str], list[str]]:
    """Return (decisions, warnings, problems) the run recorded in its sink.

    decisions pairs each object with its `<file>:<line>` location. A line
    that is not a JSON object (decisions) or a non-empty string (warnings),
    such as a write cut short, is left out and named in problems. Lines end
    at a newline only: str.splitlines() would also cut a line at a raw
    RAW_LINE_BREAKS character inside a string, which a sink line written by
    hand may hold.
    """
    decisions: list[tuple[str, dict]] = []
    warnings: list[str] = []
    problems: list[str] = []
    if run_dir is None:
        return decisions, warnings, problems
    for name, kind in ((SINK_DECISIONS, dict), (SINK_WARNINGS, str)):
        try:
            text = (run_dir / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError) as e:
            problems.append(f"sink_line_unreadable: {name}: {e}")
            continue
        for number, line in enumerate(text.split("\n"), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                value = None
            if not isinstance(value, kind) or not value:
                problems.append(f"sink_line_unreadable: {name}:{number}")
            elif kind is dict:
                decisions.append((f"{name}:{number}", value))
            else:
                warnings.append(value.strip())
    return decisions, warnings, problems


def _decision_schema(schema: dict) -> dict | None:
    """The item schema of the envelope's headless_decisions, when it has one."""
    prop = _inner_schema(schema).get("properties", {}).get("headless_decisions")
    if not isinstance(prop, dict):
        return None
    items = prop.get("items")
    return items if isinstance(items, dict) else {}


def _merged(*lists) -> list:
    """Concatenate the lists, keeping the first of any duplicate entries."""
    out, seen = [], set()
    for items in lists:
        for item in items:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def _payload_list(payload: dict, key: str, kind: type) -> list:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, kind) for item in value):
        _die(1, f"{key} must be a list of {'objects' if kind is dict else 'strings'}")
    return value


# ─── clock ──────────────────────────────────────────────────────────────────


def _utc_parts(seconds: int) -> tuple[int, int, int, int, int, int]:
    """(year, month, day, hour, minute, second) of a Unix time, in UTC."""
    days, rest = divmod(seconds, 86400)
    # Civil date from a day count (Howard Hinnant's days_from_civil inverse).
    days += 719468
    era = days // 146097
    doe = days - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    year = yoe + era * 400 + (1 if month <= 2 else 0)
    return year, month, day, rest // 3600, rest % 3600 // 60, rest % 60


def _stamps(seconds: int) -> tuple[str, str]:
    """(ISO-8601 UTC timestamp, YYYYMMDD-HHmmss file stamp) of a Unix time."""
    y, mo, d, h, mi, s = _utc_parts(seconds)
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}Z", f"{y:04d}{mo:02d}{d:02d}-{h:02d}{mi:02d}{s:02d}"


# ─── generic envelope assembly ──────────────────────────────────────────────


def _derived_exit_code(meta: dict, halt_reason):
    """The exit code the settings map `halt_reason` to, or None when they map none."""
    if halt_reason is None:
        return meta.get("success_exit_code", 0)
    if not isinstance(halt_reason, str):
        # Not a key the map can hold; the schema check names the bad value.
        return None
    return (meta.get("exit_codes") or {}).get(halt_reason)


def tolerant_payload(schema: dict, payload: dict) -> tuple[dict, list[str]]:
    """The payload without what its envelope cannot take, and a warning for each drop.

    For a caller that keeps an older helper's tolerance: a key the envelope
    has no field for is dropped (`payload_key_ignored: <key>`), and so is an
    exit_code the schema's exit_codes map decides, which the emitter then
    derives from halt_reason (`exit_code_overridden: <given> (halt_reason
    <reason> maps to <code>)` when the two differ). Such a payload still
    yields an envelope instead of a refusal.
    """
    meta = _meta_of(schema) or {}
    props = _inner_schema(schema).get("properties", {})
    kept = {k: v for k, v in payload.items() if k in props or k in PAYLOAD_ONLY_KEYS}
    notes = [f"payload_key_ignored: {k}" for k in payload if k not in kept]
    if meta.get("exit_codes") and "exit_code" in kept:
        reason = kept.get("halt_reason")
        code = _derived_exit_code(meta, reason)
        if code is not None:
            given = kept.pop("exit_code")
            if json.dumps(given) != json.dumps(code):
                notes.append(f"exit_code_overridden: {json.dumps(given)} "
                             f"(halt_reason {reason if reason is not None else 'null'} maps to {code})")
    return kept, notes


def build_envelope(schema: dict, payload: dict, *, halt: bool, stamps: dict | None = None,
                   decisions: list | None = None, warnings: list | None = None) -> dict:
    """Assemble a workflow's envelope from its payload (see the module docstring).

    `stamps` holds the timestamp, run_id and result_path the run supplies,
    None where it has none; `decisions` and `warnings` are the run's full
    lists, the payload's own entries included. Pure apart from _die.
    """
    meta = _meta_of(schema)
    stamps = stamps or {}
    decisions = decisions if decisions is not None else _payload_list(payload, "headless_decisions", dict)
    warnings = warnings if warnings is not None else _merged(
        _payload_list(payload, "warnings", str), _resolver_warning(payload))
    if meta["workflow"] == SETUP_WORKFLOW:
        return _setup_envelope(payload, halt, warnings)

    inner_schema = _inner_schema(schema)
    props = inner_schema.get("properties", {})
    required = inner_schema.get("required", [])
    skip = PAYLOAD_ONLY_KEYS + (HALT_KEYS if halt else ())
    body = {k: v for k, v in payload.items() if k not in skip}
    if halt:
        for key in HALT_KEYS:
            if key in props and key in payload:
                body[key] = payload[key]
        if "error" in props and "error" not in body:
            branch = _object_branch(props["error"])
            if branch is not None:
                error = {name: payload[ERROR_FIELDS[name]] for name in branch.get("properties", {})
                         if name in ERROR_FIELDS and payload.get(ERROR_FIELDS[name]) is not None}
                if "path" in branch.get("required", []) and "path" not in error:
                    error["path"] = "<n/a>"
                body["error"] = error
        if "status" in props and "status" not in body and meta.get("halt_status"):
            body["status"] = meta["halt_status"]

    for key in ("timestamp", "run_id", "result_path"):
        if key not in props:
            continue
        value = stamps.get(key)
        if value is not None:
            body[key] = value
        elif _allows(props[key], "null"):
            body[key] = None
        else:
            body.pop(key, None)
    for key, values in (("headless_decisions", decisions), ("warnings", warnings)):
        body.pop(key, None)
        if key in props and (values or key in required):
            body[key] = list(values)
    if "exit_code" in props and "exit_code" not in body:
        # A halt reads its halt_reason even where the schema has no field for
        # it, and never falls back to the success code.
        reason = body["halt_reason"] if "halt_reason" in body else payload.get("halt_reason")
        code = _derived_exit_code(meta, reason) if (reason is not None or not halt) else None
        if code is not None:
            body["exit_code"] = code
    for key in required:
        # exit_code is given or derived above, never a placeholder.
        if key not in body and key != "exit_code":
            value = _placeholder(props.get(key, {}), halt)
            if value is not _MISSING:
                body[key] = value
    body = _ordered(body, inner_schema)
    return {meta["wrapper"]: body} if meta.get("wrapper") else body


def _setup_envelope(payload: dict, halt: bool, warnings: list) -> dict:
    """skf-setup's envelope through its own builders, with the run's warnings added.

    Setup's own warnings stay as its builders made them, repeats included;
    the run's are appended when setup's list does not already hold them.
    """
    if halt:
        _check_halt_payload(payload, "emit-halt")
        envelope = assemble_blocked_envelope(payload["phase"], payload["reason"], payload.get("path"))
    else:
        envelope = assemble_envelope(payload)
    inner = envelope["skf_setup"]
    inner["warnings"] += [w for w in warnings if w not in inner["warnings"]]
    return envelope


def _check_halt_payload(payload: dict, label: str) -> None:
    for key in ("phase", "reason"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            _die(1, f"{label}: {key!r} must be a non-empty string")
    path = payload.get("path")
    if path is not None and not isinstance(path, str):
        _die(1, f"{label}: 'path' must be a string or omitted")


def contract_errors(schema: dict, envelope) -> list[str]:
    """Schema violations, then the rules of the emitter settings JSON Schema cannot state."""
    errors = _validate_against_schema(envelope, schema)
    if errors:
        return errors
    meta = _meta_of(schema) or {}
    wrapper = meta.get("wrapper")
    inner = envelope.get(wrapper) if wrapper else envelope
    props = _inner_schema(schema).get("properties", {}) if meta else {}
    if not isinstance(inner, dict):
        return errors
    halt_status = meta.get("halt_status")
    if halt_status and "status" in props and "halt_reason" in props:
        status, reason = inner.get("status"), inner.get("halt_reason")
        if status == halt_status and reason is None:
            errors.append(f"halt_reason must be set when status is {halt_status!r}")
        if status != halt_status and reason is not None:
            errors.append(f"halt_reason must be null when status is {status!r}; got {reason!r}")
    if meta.get("exit_codes") and "exit_code" in inner:
        reason = inner.get("halt_reason")
        expected = _derived_exit_code(meta, reason) if (reason is not None or "success_exit_code" in meta) else None
        if expected is not None and inner["exit_code"] != expected:
            errors.append(f"exit_code {inner['exit_code']!r} does not match canonical mapping "
                          f"for halt_reason {reason!r} (expected {expected})")
    return errors


def envelope_line(schema: dict, envelope: dict) -> str:
    """The prefixed one-line form: ASCII JSON, as skf-brief-skill's helper printed it.

    skf-setup's keeps its sorted keys and raw UTF-8 (emit_envelope_line).
    """
    meta = _meta_of(schema)
    if meta["workflow"] == SETUP_WORKFLOW:
        return emit_envelope_line(envelope)
    return f"{meta['prefix']}: " + json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)


# ─── result files ───────────────────────────────────────────────────────────


def _is_dir(path: Path | None) -> bool:
    """Path.is_dir() that reads a folder it may not stat as no folder."""
    try:
        return path is not None and path.is_dir()
    except OSError:
        return False


def _claim_result_path(result_dir: Path, stem: str, stamp: str) -> Path:
    """Create the run's per-run record, empty, under a name no run holds yet.

    `<stem>-<stamp>.json` when it is free, else `-2`, `-3`, ... before
    `.json`: two runs that end in the same second never overwrite each
    other's record. The exclusive create makes each claim atomic.
    """
    for n in range(1, 1000):
        path = result_dir / (f"{stem}-{stamp}.json" if n == 1 else f"{stem}-{stamp}-{n}.json")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return path
    raise OSError(f"no free file name for {stem}-{stamp}.json")


def _write_json_atomic(path: Path, value) -> None:
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


def _result_record(payload: dict, envelope: dict, timestamp, run_id, decisions: list, warnings: list):
    """The result file's content: the stamped result contract, or the envelope."""
    contract = payload.get("result_contract")
    if contract is None:
        return envelope
    record = dict(contract)
    for key in CONTRACT_DEFAULTS:
        if key not in record and key in payload:
            record[key] = payload[key]
    record["timestamp"] = timestamp
    if run_id is not None:
        record["run_id"] = run_id
    record["headless_decisions"] = list(decisions)
    record["warnings"] = list(warnings)
    return record


# ─── subcommands ────────────────────────────────────────────────────────────


def run_emit(workflow: str | None, *, halt: bool, label: str, run_dir: str | None = None,
             result_dir: str | None = None, target: str = "stdout", tolerant: bool = False) -> None:
    """Read the payload on stdin, build, check and print the envelope, write the result files.

    `tolerant` passes the payload through tolerant_payload() first, for a
    caller that keeps an older helper's tolerance.
    """
    schema, schema_path = load_workflow_schema(workflow or SETUP_WORKFLOW)
    meta = _meta_of(schema)
    workflow = meta["workflow"]
    payload = _read_stdin_json(label)
    if not isinstance(payload, dict):
        _die(1, f"{label}: the payload must be a JSON object")
    if halt:
        _check_halt_payload(payload, label)
    contract = payload.get("result_contract")
    if contract is not None and not isinstance(contract, dict):
        _die(1, f"{label}: result_contract must be an object")
    tolerated: list[str] = []
    if tolerant:
        payload, tolerated = tolerant_payload(schema, payload)

    extra: list[str] = []
    stem = meta.get("result_file")
    run_path = Path(run_dir) if run_dir else None
    if workflow == SETUP_WORKFLOW and not halt:
        payload = fold_staged(payload, read_staged(run_path))
    result_path_dir = Path(result_dir) if result_dir else None
    if result_path_dir is not None and not stem:
        # Refusing would leave a halt that passed the flag by mistake with no line.
        extra.append(f"result_dir_ignored: {workflow} writes no result file")
        result_path_dir = None
    writes = _is_dir(result_path_dir)
    run_id = None
    if run_path is not None:
        name, prefix = run_path.name, f"{workflow}-"
        run_id = name[len(prefix):] if name.startswith(prefix) and len(name) > len(prefix) else name

    timestamp = file_stamp = None
    if writes or "timestamp" in _inner_schema(schema).get("properties", {}):
        timestamp, file_stamp = _stamps(int(time.time()))

    sink_decisions, sink_warnings, problems = read_sink(run_path)
    item_schema = _decision_schema(schema)
    valid = []
    for where, decision in sink_decisions:
        errors = _validate_against_schema(decision, item_schema) if item_schema else []
        if errors:
            problems.append(f"headless_decision_invalid: {where}: {errors[0]}")
        else:
            valid.append(decision)
    decisions = _merged(_payload_list(payload, "headless_decisions", dict), valid)

    per_run = None
    if writes:
        try:
            per_run = _claim_result_path(result_path_dir, stem, file_stamp)
        except OSError as e:
            extra.append(f"result_file_write_failed: {result_path_dir.as_posix()}: {e.strerror or e}")

    def assemble() -> tuple[dict, list]:
        warnings = _merged(_payload_list(payload, "warnings", str), _resolver_warning(payload),
                           sink_warnings, problems, tolerated, extra)
        stamps = {"timestamp": timestamp, "run_id": run_id,
                  "result_path": per_run.as_posix() if per_run else None}
        envelope = build_envelope(schema, payload, halt=halt, stamps=stamps,
                                  decisions=decisions, warnings=warnings)
        errors = contract_errors(schema, envelope)
        if errors:
            if per_run is not None:
                try:
                    per_run.unlink()
                except OSError:
                    pass
            code = 2 if workflow == SETUP_WORKFLOW else 1
            _die(code, f"{label}: the {workflow} envelope fails {schema_path.name}: {'; '.join(errors)}")
        return envelope, warnings

    envelope, warnings = assemble()
    if per_run is not None:
        record = _result_record(payload, envelope, timestamp, run_id, decisions, warnings)
        latest = result_path_dir / f"{stem}-latest.json"
        for path in (per_run, latest):
            try:
                _write_json_atomic(path, record)
            except OSError as e:
                extra.append(f"result_file_write_failed: {path.as_posix()}: {e.strerror or e}")
                if path == per_run:
                    try:
                        per_run.unlink()
                    except OSError:
                        pass
                    per_run = None
                break
        if extra:
            envelope, _ = assemble()
    print(envelope_line(schema, envelope), file=sys.stderr if target == "stderr" else sys.stdout)


def cmd_record(args) -> None:
    """Append one decision or one warning to the run's sink, one JSON value per line."""
    run_dir = Path(args.run_dir)
    if args.warning is not None:
        value = args.warning.strip()
        if not value:
            _die(1, "record: --warning must be a non-empty string")
        name = SINK_WARNINGS
    else:
        value = _read_stdin_json("record")
        if not isinstance(value, dict) or not value:
            _die(1, "record: --decision reads one non-empty JSON object on stdin")
        if args.workflow:
            schema, schema_path = load_workflow_schema(args.workflow)
            item_schema = _decision_schema(schema)
            if item_schema is None:
                _die(1, f"record: {schema_path.name} has no headless_decisions")
            errors = _validate_against_schema(value, item_schema)
            if errors:
                _die(1, f"record: the decision fails {schema_path.name}: {'; '.join(errors)}")
        name = SINK_DECISIONS
    # ASCII only: a raw RAW_LINE_BREAKS character would split the line for a
    # reader that breaks lines there.
    line = json.dumps(value, separators=(",", ":"), ensure_ascii=True) + "\n"
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / name, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError as e:
        _die(1, f"record: cannot append to {(run_dir / name).as_posix()}: {e.strerror or e}")


def cmd_validate(workflow: str | None) -> None:
    envelope = _read_stdin_json("validate")
    schema, _ = load_workflow_schema(workflow or SETUP_WORKFLOW)
    errors = contract_errors(schema, envelope)
    if errors:
        _die(1, "; ".join(errors))


def cmd_render_report(run_dir: str | None, tier_rules: str | None) -> None:
    """Print skf-setup's FORGE STATUS banner for the payload on stdin."""
    payload = _read_stdin_json("render-report")
    if not isinstance(payload, dict):
        _die(1, "render-report: the payload must be a JSON object")
    payload = fold_staged(payload, read_staged(Path(run_dir) if run_dir else None))
    copy = load_tier_rules(Path(tier_rules) if tier_rules else TIER_RULES_FILE)
    print("\n".join(render_report(payload, copy)))


def assemble_blocked_envelope(phase: str, reason: str, path: str | None = None) -> dict:
    """Assemble a minimal status='blocked' envelope for a halt.

    Used by every halt that names a phase (On Activation and steps 1, 1b,
    2 and 3), which has no complete run to report. Every other required
    field gets a placeholder, as the schema describes, so the envelope
    still passes schema validation and pipelines can branch on
    `status: "blocked"` and inspect `error` for context.
    """
    error = {
        "phase": phase,
        "path": path or "<n/a>",
        "reason": reason,
    }
    return {
        "skf_setup": {
            "status": _compute_status(error, None),
            "tier": "Quick",
            "previous_tier": None,
            "tier_changed": False,
            "tools": {"ast_grep": False, "gh_cli": False, "qmd": False, "ccc": False},
            "tools_added": [],
            "tools_removed": [],
            "config_path": path or "<unknown — halt before config_path resolved>",
            "ccc_index": {"status": "none", "indexed_path": None, "file_count": None},
            "files_written": [],
            "tier_override_active": False,
            "tier_override_invalid": False,
            "require_tier_satisfied": None,
            "warnings": [],
            "error": error,
        }
    }


def cmd_emit_blocked() -> None:
    """Emit skf-setup's blocked envelope: `emit-halt --workflow skf-setup`.

    Designed for the halts (uv missing, config.yaml missing, a failed write,
    etc.) where the regular `emit` subcommand can't run because the run has
    no complete tier/tools/config_path to report.
    """
    run_emit(SETUP_WORKFLOW, halt=True, label="emit-blocked")


def _force_utf8(*streams) -> None:
    """Reconfigure JSON-carrying streams to UTF-8.

    A default Windows console decodes stdio as cp1252, which cannot carry
    non-ASCII JSON (ensure_ascii=False output, raw UTF-8 input). Preserves
    each stream's existing error handler — reconfigure(encoding=...) alone
    would reset it to 'strict', downgrading e.g. an already-UTF-8 stderr on
    Linux. For stdin this must run before the first read. Skips in-process
    test doubles without reconfigure().
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main() -> None:
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")
    p_emit = sub.add_parser("emit",          help="Build a run's envelope from its context payload (default).")
    p_halt = sub.add_parser("emit-halt",     help="Build a HARD HALT's envelope from its halt payload.")
    sub.add_parser("emit-blocked",           help="Emit skf-setup's status='blocked' envelope for early-halt paths.")
    p_record = sub.add_parser("record",      help="Append an auto-decision or a warning to the run's sink.")
    p_validate = sub.add_parser("validate",  help="Validate an envelope payload against the schema.")
    p_render = sub.add_parser("render-report", help="Print skf-setup's FORGE STATUS banner for its payload.")
    for p in (p_emit, p_halt):
        p.add_argument("--workflow", required=p is p_halt, default=None,
                       help="Workflow folder name or schema stem (emit: skf-setup when omitted).")
        p.add_argument("--run-dir", default=None,
                       help="The run folder that holds the sink (and skf-setup's staged helper outputs).")
        p.add_argument("--result-dir", default=None,
                       help="Write the per-run and -latest result files here when the folder exists.")
        p.add_argument("--target", choices=["stdout", "stderr"], default="stdout",
                       help="Stream for the envelope line (default stdout).")
    p_record.add_argument("--run-dir", required=True, help="The run folder that holds the sink.")
    p_record.add_argument("--workflow", default=None,
                          help="Check a decision against this workflow's headless_decisions schema.")
    kind = p_record.add_mutually_exclusive_group(required=True)
    kind.add_argument("--decision", action="store_true", help="Read one decision object on stdin.")
    kind.add_argument("--warning", default=None, help="The warning text.")
    p_validate.add_argument("--workflow", default=None,
                            help="Workflow folder name or schema stem (skf-setup when omitted).")
    p_render.add_argument("--run-dir", default=None, help="The setup run folder that holds the staged helper outputs.")
    p_render.add_argument("--tier-rules", default=None,
                          help="skf-setup's references/tier-rules.md (default: beside this script's folder).")
    args = parser.parse_args()

    cmd = args.cmd or "emit"
    if cmd in ("emit", "emit-halt"):
        run_emit(getattr(args, "workflow", None), halt=cmd == "emit-halt", label=cmd,
                 run_dir=getattr(args, "run_dir", None), result_dir=getattr(args, "result_dir", None),
                 target=getattr(args, "target", "stdout"))
    elif cmd == "emit-blocked":
        cmd_emit_blocked()
    elif cmd == "record":
        cmd_record(args)
    elif cmd == "validate":
        cmd_validate(args.workflow)
    elif cmd == "render-report":
        cmd_render_report(args.run_dir, args.tier_rules)


if __name__ == "__main__":
    main()
