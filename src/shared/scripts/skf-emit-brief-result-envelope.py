# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Emit Brief Result Envelope — Schema-locked headless output for skf-brief-skill.

Replaces the prose-driven envelope assembly in `src/skf-brief-skill/steps-c/
step-05-write-brief.md` §4b with one Python invocation. The envelope contract
(SKF_BRIEF_RESULT_JSON) is documented in src/skf-brief-skill/SKILL.md Result
Contract section.

LLM-rendered envelopes risk silent schema drift on every invocation —
a pipeline that grep's `SKF_BRIEF_RESULT_JSON: {…}` out of the workflow
log can break if the model decides to rename a key, reorder properties,
or swap a null for an empty string. This script is the single source of
truth: it takes a context payload as JSON on stdin, derives the
exit_code from the halt_reason deterministically, validates the
assembled envelope against the JSON Schema at
`src/shared/scripts/schemas/skf-brief-result-envelope.v1.json`, and
emits the line in a fixed shape.

Subcommands:

  emit       Read context payload as JSON on stdin, derive exit_code,
             validate against the schema, emit the
             `SKF_BRIEF_RESULT_JSON: {one-line JSON}` prefix line on
             stdout (or stderr if --target=stderr). Default subcommand.

  validate   Read an envelope (without the prefix) as JSON on stdin
             and verify it against the schema. Silent + exit 0 on
             success; non-zero exit + stderr error on failure. Useful
             for paranoid pipelines that want to validate a received
             envelope before consuming it.

Context payload shape (consumed by `emit`):

  {
    "status":      "success" | "error",
    "brief_path":  "/abs/path/skill-brief.yaml" | null,
    "skill_name":  "marked",
    "version":     "1.2.3" | null,
    "language":    "javascript" | null,
    "scope_type":  "public-api" | null,
    "halt_reason": null | "input-missing" | "input-invalid" |
                   "forge-tier-missing" | "target-inaccessible" |
                   "gh-auth-failed" | "write-failed" |
                   "overwrite-cancelled" | "user-cancelled"
  }

The caller does NOT supply exit_code — the script derives it from
halt_reason via the canonical mapping (null→0; input-*→2;
forge-tier-missing/target-inaccessible/gh-auth-failed→3;
write-failed→4; overwrite-cancelled→5; user-cancelled→6).

Cross-platform: pure stdlib, no third-party deps.

CLI:

  echo '{...}' | uv run skf-emit-brief-result-envelope.py emit
  echo '{...}' | uv run skf-emit-brief-result-envelope.py emit --target stderr
  echo '{...}' | uv run skf-emit-brief-result-envelope.py validate
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

PREFIX = "SKF_BRIEF_RESULT_JSON: "

VALID_STATUS = {"success", "error"}
VALID_HALT_REASONS = {
    None,
    "input-missing",
    "input-invalid",
    "forge-tier-missing",
    "target-inaccessible",
    "gh-auth-failed",
    "write-failed",
    "overwrite-cancelled",
    "user-cancelled",
}
VALID_SCOPE_TYPES = {
    None,
    "full-library",
    "specific-modules",
    "public-api",
    "component-library",
    "reference-app",
    "docs-only",
}

# Canonical halt_reason → exit_code mapping (mirrors SKILL.md Exit Codes table).
HALT_TO_EXIT = {
    None: 0,
    "input-missing": 2,
    "input-invalid": 2,
    "forge-tier-missing": 3,
    "target-inaccessible": 3,
    "gh-auth-failed": 3,
    "write-failed": 4,
    "overwrite-cancelled": 5,
    "user-cancelled": 6,
}

# Envelope key order — fixed so byte-stable diffs are possible.
KEY_ORDER = [
    "status",
    "brief_path",
    "skill_name",
    "version",
    "language",
    "scope_type",
    "exit_code",
    "halt_reason",
]


def _die(message: str, code: int = 1) -> None:
    sys.stderr.write(f"skf-emit-brief-result-envelope: {message}\n")
    sys.exit(code)


def assemble(ctx: dict[str, Any]) -> dict[str, Any]:
    """Build the envelope from a context payload, deriving exit_code."""
    status = ctx.get("status")
    if status not in VALID_STATUS:
        _die(f"status must be one of {sorted(VALID_STATUS)}; got {status!r}")

    halt_reason = ctx.get("halt_reason")
    if halt_reason not in VALID_HALT_REASONS:
        _die(
            f"halt_reason must be one of {sorted(r for r in VALID_HALT_REASONS if r is not None)} or null; "
            f"got {halt_reason!r}"
        )

    if status == "success" and halt_reason is not None:
        _die(f"halt_reason must be null when status is 'success'; got {halt_reason!r}")
    if status == "error" and halt_reason is None:
        _die("halt_reason must be set when status is 'error'")

    scope_type = ctx.get("scope_type")
    if scope_type not in VALID_SCOPE_TYPES:
        _die(
            f"scope_type must be one of {sorted(t for t in VALID_SCOPE_TYPES if t is not None)} or null; "
            f"got {scope_type!r}"
        )

    skill_name = ctx.get("skill_name")
    if not skill_name or not isinstance(skill_name, str):
        _die(f"skill_name is required and must be a non-empty string; got {skill_name!r}")

    envelope = {
        "status": status,
        "brief_path": ctx.get("brief_path"),
        "skill_name": skill_name,
        "version": ctx.get("version"),
        "language": ctx.get("language"),
        "scope_type": scope_type,
        "exit_code": HALT_TO_EXIT[halt_reason],
        "halt_reason": halt_reason,
    }
    # Re-emit in canonical key order
    return {k: envelope[k] for k in KEY_ORDER}


def validate(envelope: dict[str, Any]) -> None:
    """Validate an envelope dict against the schema. Exits non-zero on failure."""
    required = set(KEY_ORDER)
    missing = required - set(envelope.keys())
    if missing:
        _die(f"envelope missing required keys: {sorted(missing)}")
    extra = set(envelope.keys()) - required
    if extra:
        _die(f"envelope has unexpected keys: {sorted(extra)}")
    if envelope.get("status") not in VALID_STATUS:
        _die(f"status invalid: {envelope.get('status')!r}")
    if envelope.get("halt_reason") not in VALID_HALT_REASONS:
        _die(f"halt_reason invalid: {envelope.get('halt_reason')!r}")
    if envelope.get("scope_type") not in VALID_SCOPE_TYPES:
        _die(f"scope_type invalid: {envelope.get('scope_type')!r}")
    if envelope.get("exit_code") not in {0, 2, 3, 4, 5}:
        _die(f"exit_code invalid: {envelope.get('exit_code')!r}")
    expected_exit = HALT_TO_EXIT[envelope.get("halt_reason")]
    if envelope.get("exit_code") != expected_exit:
        _die(
            f"exit_code {envelope.get('exit_code')!r} does not match canonical mapping "
            f"for halt_reason {envelope.get('halt_reason')!r} (expected {expected_exit})"
        )
    if not envelope.get("skill_name") or not isinstance(envelope.get("skill_name"), str):
        _die("skill_name must be a non-empty string")


def cmd_emit(target_stream: str) -> int:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        _die("emit: empty stdin (expected JSON context payload)")
    try:
        ctx = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"emit: invalid JSON on stdin: {e}")
    if not isinstance(ctx, dict):
        _die("emit: context payload must be a JSON object")

    envelope = assemble(ctx)
    line = PREFIX + json.dumps(envelope, separators=(",", ":"))
    if target_stream == "stderr":
        print(line, file=sys.stderr)
    else:
        print(line)
    return 0


def cmd_validate() -> int:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        _die("validate: empty stdin (expected envelope JSON)")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"validate: invalid JSON on stdin: {e}")
    if not isinstance(envelope, dict):
        _die("validate: envelope must be a JSON object")
    validate(envelope)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skf-emit-brief-result-envelope",
        description="Schema-locked SKF_BRIEF_RESULT_JSON envelope emitter for skf-brief-skill.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_emit = sub.add_parser("emit", help="Read context JSON on stdin, emit prefixed envelope line")
    p_emit.add_argument(
        "--target",
        choices=["stdout", "stderr"],
        default="stdout",
        help="Output stream for the prefixed envelope line. step-05 §4b uses stdout on success and stderr on HARD HALT.",
    )

    sub.add_parser("validate", help="Read envelope JSON on stdin, exit 0 if schema-valid")

    args = parser.parse_args()

    if args.cmd == "emit":
        return cmd_emit(args.target)
    elif args.cmd == "validate":
        return cmd_validate()
    return 2


if __name__ == "__main__":
    sys.exit(main())
