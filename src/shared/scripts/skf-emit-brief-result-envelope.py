# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Emit Brief Result Envelope: skf-brief-skill's name for the shared emitter.

An alias of `skf-emit-result-envelope.py ... --workflow skf-brief-skill`,
kept so the brief step files that call it keep working. The envelope
contract (SKF_BRIEF_RESULT_JSON) is documented in src/skf-brief-skill/SKILL.md
Result Contract section; its schema,
`schemas/skf-brief-result-envelope.v1.json`, holds the whole contract,
including the halt_reason to exit_code mapping, and the shared emitter
enforces it. Nothing here restates it.

Subcommands:

  emit       Read the context payload as JSON on stdin, derive exit_code
             from halt_reason, validate against the schema, emit the
             `SKF_BRIEF_RESULT_JSON: {one-line JSON}` prefix line on
             stdout (or stderr if --target=stderr). Same as
             `skf-emit-result-envelope.py emit --workflow skf-brief-skill`,
             except that it keeps the tolerance of the helper it replaced
             (below).

  validate   Read an envelope (without the prefix) as JSON on stdin and
             verify it against the schema. Silent + exit 0 on success;
             non-zero exit + stderr error on failure. Same as
             `skf-emit-result-envelope.py validate --workflow skf-brief-skill`.

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
                   "overwrite-cancelled" | "user-cancelled",
    "mode":        null | "auto",
    "warnings":    ["..."],
    "customization_resolver_unavailable": "reason" | null
  }

The caller does NOT supply exit_code: the emitter derives it from
halt_reason with the schema's mapping. `warnings` and a
`customization_resolver_unavailable` reason land in the envelope's
optional `warnings` list, which is left out while it is empty.

Like the helper it replaced, `emit` refuses no payload for a key the
envelope has no field for, or for an exit_code it typed: the key is
dropped with the warning `payload_key_ignored: <key>`, and the exit_code
is derived from halt_reason as always, with the warning
`exit_code_overridden: <given> (halt_reason <reason> maps to <code>)` when
the two differ. A halt that stages one key too many still emits its line.
The line is ASCII JSON, so a payload with no such key prints the line the
old helper printed, byte for byte.

CLI:

  echo '{...}' | uv run skf-emit-brief-result-envelope.py emit
  echo '{...}' | uv run skf-emit-brief-result-envelope.py emit --target stderr
  echo '{...}' | uv run skf-emit-brief-result-envelope.py validate
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

WORKFLOW = "skf-brief-skill"
PREFIX = "SKF_BRIEF_RESULT_JSON: "
EMITTER = Path(__file__).resolve().parent / "skf-emit-result-envelope.py"


def _emitter():
    """Load the shared emitter from beside this script (source tree or install)."""
    spec = importlib.util.spec_from_file_location("skf_emit_result_envelope", EMITTER)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"skf-emit-brief-result-envelope: cannot load {EMITTER}\n")
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _emitter()


def assemble(ctx: dict[str, Any]) -> dict[str, Any]:
    """Build the envelope from a context payload, deriving exit_code. Exits non-zero when invalid."""
    schema, schema_path = core.load_workflow_schema(WORKFLOW)
    ctx, tolerated = core.tolerant_payload(schema, ctx)
    warnings = core._merged(core._payload_list(ctx, "warnings", str), core._resolver_warning(ctx), tolerated)
    envelope = core.build_envelope(schema, ctx, halt=False, warnings=warnings)
    errors = core.contract_errors(schema, envelope)
    if errors:
        core._die(1, f"the {WORKFLOW} envelope fails {schema_path.name}: {'; '.join(errors)}")
    return envelope


def validate(envelope: dict[str, Any]) -> None:
    """Validate an envelope dict against the schema. Exits non-zero on failure."""
    schema, _ = core.load_workflow_schema(WORKFLOW)
    errors = core.contract_errors(schema, envelope)
    if errors:
        core._die(1, "; ".join(errors))


def main() -> int:
    core._force_utf8(sys.stdin, sys.stdout, sys.stderr)
    parser = argparse.ArgumentParser(
        prog="skf-emit-brief-result-envelope",
        description="SKF_BRIEF_RESULT_JSON envelope emitter for skf-brief-skill (alias of skf-emit-result-envelope.py).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_emit = sub.add_parser("emit", help="Read context JSON on stdin, emit prefixed envelope line")
    p_emit.add_argument(
        "--target",
        choices=["stdout", "stderr"],
        default="stdout",
        help="Output stream for the prefixed envelope line. step 5 §4b uses stdout on success and stderr on HARD HALT.",
    )

    sub.add_parser("validate", help="Read envelope JSON on stdin, exit 0 if schema-valid")

    args = parser.parse_args()

    if args.cmd == "emit":
        core.run_emit(WORKFLOW, halt=False, label="emit", target=args.target, tolerant=True)
        return 0
    if args.cmd == "validate":
        core.cmd_validate(WORKFLOW)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
