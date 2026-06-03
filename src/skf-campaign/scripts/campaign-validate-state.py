# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml", "jsonschema>=4.0"]
# ///
"""Campaign Validate State — schema check for _campaign-state.yaml on disk.

Replaces the per-step "mentally validate the loaded state against the schema"
prose with a deterministic check. Every campaign step that loads state runs
this once on entry instead of asking the LLM to validate a draft-07 schema
(nested objects, enums, additionalProperties:false, date-time) by hand — the
exact check an LLM does unreliably and which, when wrong, silently corrupts a
multi-session campaign.

Loads the campaign state YAML, validates it against
`assets/campaign-state-schema.json` (resolved relative to this script unless
`--schema-file` overrides), and emits skill-friendly error records the calling
step can forward verbatim.

CLI:
  uv run campaign-validate-state.py --state-file <path>
  uv run campaign-validate-state.py --state-file <path> --schema-file <path>

Output (JSON on stdout):
  {
    "valid": bool,
    "errors":   [{"field": "campaign.current_stage", "message": "..."}, ...],
    "halt_reason": "state-missing" | "state-malformed" | "state-invalid" | null
  }

Exit codes:
  0  valid (errors empty)
  1  invalid (schema violations) OR file/yaml load failed
  2  configuration error (schema file missing or unreadable)
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "assets" / "campaign-state-schema.json"


def _emit(envelope: dict) -> None:
    json.dump(envelope, sys.stdout, separators=(",", ":"), default=str)
    sys.stdout.write("\n")


def _load_yaml_text(text: str) -> tuple[Any, str | None]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"State is not valid YAML: {exc}"
    if data is None:
        return None, "State file is empty"
    if not isinstance(data, dict):
        return None, f"State root must be a YAML mapping; got {type(data).__name__}"
    return data, None


def _field_path(error_path) -> str:
    parts: list[str] = []
    for p in error_path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(f".{p}" if parts else str(p))
    return "".join(parts) or "(root)"


def _translate(err) -> dict:
    field = _field_path(err.absolute_path)
    validator = err.validator
    inst = err.instance

    if validator == "required":
        missing = err.message.split("'")[1] if "'" in err.message else "(unknown)"
        return {
            "field": missing,
            "message": f"State validation failed: missing required field `{missing}`.",
        }
    if validator == "enum":
        return {
            "field": field,
            "message": (
                f"State validation failed: `{field}` value `{inst}` is not one of "
                f"{err.validator_value}."
            ),
        }
    if validator == "type":
        if isinstance(inst, datetime.date) and "string" in str(err.validator_value):
            return {
                "field": field,
                "message": (
                    f"State validation failed: `{field}` parsed as a YAML date, not a "
                    f"string. Quote it (e.g. `'2026-05-01T00:00:00Z'`)."
                ),
            }
        return {
            "field": field,
            "message": (
                f"State validation failed: `{field}` has type `{type(inst).__name__}`, "
                f"expected `{err.validator_value}`."
            ),
        }
    if validator == "additionalProperties":
        return {
            "field": field,
            "message": f"State validation failed: `{field}` — {err.message}",
        }
    if validator in ("minimum", "maximum"):
        return {
            "field": field,
            "message": f"State validation failed: `{field}` value `{inst}` violates {validator} `{err.validator_value}`.",
        }
    return {
        "field": field,
        "message": f"State validation failed: `{field}` — {err.message}",
    }


def validate_state(state: dict, schema: dict) -> dict:
    validator = Draft7Validator(schema)
    errors = [
        _translate(err)
        for err in sorted(validator.iter_errors(state), key=lambda e: list(e.absolute_path))
    ]
    return {"valid": not errors, "errors": errors}


def run(state_file: str, schema_file: str | None = None) -> int:
    schema_path = Path(schema_file) if schema_file else DEFAULT_SCHEMA_PATH
    if not schema_path.is_file():
        _emit(
            {
                "valid": False,
                "errors": [{"field": "(schema)", "message": f"Schema not found at `{schema_path}`."}],
                "halt_reason": "state-invalid",
            }
        )
        return 2
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit(
            {
                "valid": False,
                "errors": [{"field": "(schema)", "message": f"Schema unreadable: {exc}"}],
                "halt_reason": "state-invalid",
            }
        )
        return 2

    state_path = Path(state_file)
    if not state_path.is_file():
        _emit(
            {
                "valid": False,
                "errors": [{"field": "(file)", "message": f"State not found at `{state_path}`."}],
                "halt_reason": "state-missing",
            }
        )
        return 1

    state, load_err = _load_yaml_text(state_path.read_text(encoding="utf-8"))
    if load_err is not None:
        _emit(
            {
                "valid": False,
                "errors": [{"field": "(file)", "message": load_err}],
                "halt_reason": "state-malformed",
            }
        )
        return 1

    result = validate_state(state, schema)
    if not result["valid"]:
        _emit({**result, "halt_reason": "state-invalid"})
        return 1

    _emit({**result, "halt_reason": None})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-validate-state",
        description="Validate _campaign-state.yaml against the campaign state schema.",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    parser.add_argument(
        "--schema-file",
        help="Path to campaign-state-schema.json (defaults to the bundled schema)",
    )
    args = parser.parse_args(argv)
    return run(args.state_file, args.schema_file)


if __name__ == "__main__":
    raise SystemExit(main())
