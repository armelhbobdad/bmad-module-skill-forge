# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Emit Result Envelope — Schema-locked headless output for skf-setup.

Replaces the prose-driven envelope assembly in `src/skf-setup/references/
report.md` §4 with one Python invocation. The envelope contract
(SKF_SETUP_RESULT_JSON) was added to step 4 in PR #247, extended in
PR #248 (header / outputs / failure modes), and extended again in this
PR (previous_tier, tier_changed, tools_added, tools_removed, error).

LLM-rendered envelopes risk silent schema drift on every invocation —
a pipeline that grep's `SKF_SETUP_RESULT_JSON: {…}` out of the workflow
log can break if the model decides to rename a key or rearrange a
nested structure. This script is the single source of truth: it takes
a context payload as JSON on stdin, computes derived fields
deterministically, and emits the envelope in a fixed shape that
matches the JSON Schema at
`src/shared/scripts/schemas/skf-setup-result-envelope.v1.json`.

Subcommands:

  emit       Read context payload as JSON on stdin, derive missing
             fields (tools_added/removed, tier_changed), assemble the
             envelope, emit `SKF_SETUP_RESULT_JSON: {one-line JSON}`
             on stdout. Default subcommand.

  validate   Read an envelope (without the prefix) as JSON on stdin
             and verify it against the documented schema. No stdout
             on success; non-zero exit + stderr error on failure.
             Useful for paranoid pipelines that want to validate a
             received envelope before consuming it.

Context payload shape (consumed by `emit`):

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
    "ccc_exclusion_warnings":        ["string", ...],
    "ccc_registry_stale_removed":    ["/path", ...],
    "ccc_indexing_failed_reason":    "string|null",
    "orphan_auto_resolution":        null|{"action": "keep|remove", "count": int, "source": "headless-default|orphan-action-flag"},
    "error":                         null|{"phase","path","reason"}
  }

  When the step-3 orphan-removal gate is resolved non-interactively
  (headless default Keep, or an explicit --orphan-action), pass
  `orphan_auto_resolution` so the audit trail lands in `warnings` —
  most importantly when the destructive `remove` ran headlessly, which a
  pipeline otherwise could not distinguish from a no-op by reading the
  envelope alone.

Caller does NOT need to compute warnings, tools_added/removed, or
tier_changed — the script derives them from the inputs above.

CLI — invoke via `uv run` for invocation consistency with sibling
scripts (PEP 723 inline metadata is honored automatically; this script
declares dependencies = [] so technically `python3` works too, but
prefer `uv run` so all 5 cutover scripts share one canonical invocation
pattern documented in docs/getting-started.md):

  echo '{...context payload...}' | uv run skf-emit-result-envelope.py emit
  echo '{"skf_setup":{...}}' | uv run skf-emit-result-envelope.py validate

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
from pathlib import Path


ENVELOPE_PREFIX = "SKF_SETUP_RESULT_JSON: "
SCHEMA_FILE = Path(__file__).parent / "schemas" / "skf-setup-result-envelope.v1.json"
TOOL_KEYS = ("ast_grep", "gh_cli", "qmd", "ccc")
VALID_TIERS = ("Quick", "Forge", "Forge+", "Deep")
VALID_FILES = ("forge-tier.yaml", "preferences.yaml", "settings.yml", "ccc_index")
VALID_CCC_STATUS = ("fresh", "created", "failed", "none", "skipped")


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


def _assemble_warnings(payload: dict) -> list[str]:
    """Fold every documented warning source into the envelope's warnings array.

    Matches the field-rules block in step 4 §4 — pipelines should only need
    to consult `warnings` to surface non-fatal issues.
    """
    warnings: list[str] = []
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
    return warnings


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
            "files_written": _normalize_files_written(payload.get("files_written")),
            "tier_override_active": bool(payload.get("tier_override_active", False)),
            "tier_override_invalid": bool(payload.get("tier_override_invalid", False)),
            "require_tier_satisfied": require_tier_satisfied,
            "warnings": _assemble_warnings(payload),
            "error": error,
        }
    }


def _compute_status(error: dict | None, require_tier_satisfied) -> str:
    """Derive the single-field status from error + require_tier_satisfied.

    - 'write_failure' when error.phase signals a file-write failure
    - 'blocked'       when error is non-null but not a write failure
    - 'tier_failure'  when require_tier_satisfied is False
    - 'success'       otherwise
    """
    if error is not None:
        phase = (error.get("phase") or "").lower()
        if "write" in phase or phase.endswith("forge-tier.yaml") or phase.endswith("preferences.yaml"):
            return "write_failure"
        return "blocked"
    if require_tier_satisfied is False:
        return "tier_failure"
    return "success"


def emit_envelope_line(envelope: dict) -> str:
    """Serialize the envelope as one prefixed line. No embedded newlines, sort_keys=True for determinism."""
    body = json.dumps(envelope, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    if "\n" in body:
        _die(2, "envelope serialization produced embedded newline (should be impossible)")
    return ENVELOPE_PREFIX + body


# ─── minimal stdlib JSON Schema validator ───────────────────────────────────


def _load_schema() -> dict:
    if not SCHEMA_FILE.exists():
        _die(2, f"schema file missing: {SCHEMA_FILE}")
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _validate_against_schema(value, schema: dict, path: str = "$") -> list[str]:
    """Return a list of error strings (empty = valid).

    Implements only the subset of Draft 2020-12 features used by our envelope
    schema: type, enum, oneOf, properties, additionalProperties, required,
    items, uniqueItems, minLength, minimum. Sufficient to catch every
    violation our schema can express; not a general-purpose validator.
    """
    errors: list[str] = []

    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not _validate_against_schema(value, sub, path))
        if matches != 1:
            errors.append(f"{path}: matched {matches} of {len(schema['oneOf'])} oneOf branches (expected exactly 1)")
        return errors

    expected_type = schema.get("type")
    if expected_type is not None:
        if not _matches_type(value, expected_type):
            errors.append(f"{path}: expected type {expected_type}, got {type(value).__name__}")
            return errors

    if "enum" in schema:
        if value not in schema["enum"]:
            errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")

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


# ─── subcommands ────────────────────────────────────────────────────────────


def cmd_emit() -> None:
    payload = _read_stdin_json("emit")
    envelope = assemble_envelope(payload)
    schema = _load_schema()
    errors = _validate_against_schema(envelope, schema)
    if errors:
        _die(2, f"assembled envelope failed schema validation (this is a bug): {errors}")
    print(emit_envelope_line(envelope))


def cmd_validate() -> None:
    envelope = _read_stdin_json("validate")
    schema = _load_schema()
    errors = _validate_against_schema(envelope, schema)
    if errors:
        _die(1, "; ".join(errors))


def assemble_blocked_envelope(phase: str, reason: str, path: str | None = None) -> dict:
    """Assemble a minimal status='blocked' envelope for early-halt paths.

    Used when On Activation or step 2 halts before the regular envelope
    construction has the inputs it needs (no tier, no detected tools,
    no config_path). Every other required field gets a documented sentinel
    so the envelope still passes schema validation and pipelines can
    branch on `status: "blocked"` and inspect `error` for context.
    """
    return {
        "skf_setup": {
            "status": "blocked",
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
            "error": {
                "phase": phase,
                "path": path or "<n/a>",
                "reason": reason,
            },
        }
    }


def cmd_emit_blocked() -> None:
    """Emit a blocked envelope. Reads `phase`, `reason`, optional `path` from stdin JSON.

    Designed for early-halt paths (uv missing, config.yaml missing, etc.) where
    the regular `emit` subcommand can't run because tier/tools/config_path are
    not yet known.
    """
    payload = _read_stdin_json("emit-blocked")
    phase = payload.get("phase")
    reason = payload.get("reason")
    if not isinstance(phase, str) or not phase:
        _die(1, "emit-blocked: 'phase' must be a non-empty string")
    if not isinstance(reason, str) or not reason:
        _die(1, "emit-blocked: 'reason' must be a non-empty string")
    path = payload.get("path")
    if path is not None and not isinstance(path, str):
        _die(1, "emit-blocked: 'path' must be a string or omitted")
    envelope = assemble_blocked_envelope(phase, reason, path)
    schema = _load_schema()
    errors = _validate_against_schema(envelope, schema)
    if errors:
        _die(2, f"assembled blocked envelope failed schema validation: {errors}")
    print(emit_envelope_line(envelope))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("emit",          help="Build envelope from context payload (default).")
    sub.add_parser("emit-blocked",  help="Emit minimal status='blocked' envelope for early-halt paths.")
    sub.add_parser("validate",      help="Validate an envelope payload against the schema.")
    args = parser.parse_args()

    cmd = args.cmd or "emit"
    if cmd == "emit":
        cmd_emit()
    elif cmd == "emit-blocked":
        cmd_emit_blocked()
    elif cmd == "validate":
        cmd_validate()


if __name__ == "__main__":
    main()
