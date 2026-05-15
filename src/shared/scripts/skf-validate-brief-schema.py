# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "jsonschema>=4.0"]
# ///
"""SKF Validate Brief Schema — schema check for a skill-brief.yaml on disk.

Loads `skill-brief.yaml` from a path (or from stdin/inline-YAML), validates
it against `src/shared/scripts/schemas/skill-brief.v1.json`, and applies the
two conditional rules from `skf-create-skill/references/load-brief.md §3`
that the JSON schema doesn't express today:

  - When `source_type == "docs-only"`: `doc_urls` must have ≥1 entry, and
    `source_authority` must be `community` (the prose says it is "forced
    to community" — we surface a warning when it disagrees rather than
    silently rewriting).
  - `version` must be present AND non-empty AND not whitespace-only. The
    schema rejects empty strings via its semver pattern, but a string that
    only contains whitespace would slip past a naive presence check; we
    catch that case explicitly so the downstream directory-resolution code
    doesn't produce `{name}//` paths.

The script produces skill-friendly error messages — translating raw
jsonschema diagnostics into the "Brief validation failed: ..." form the
calling stage prose already uses. Calling stages can read `errors[]`
directly and forward the `message` field to the user.

CLI:
  uv run skf-validate-brief-schema.py <path/to/skill-brief.yaml>
  cat brief.yaml | uv run skf-validate-brief-schema.py -
  uv run skf-validate-brief-schema.py --yaml '<inline yaml>'

Output (JSON on stdout):
  {
    "valid": bool,
    "errors":   [{"field": "...", "message": "..."}, ...],
    "warnings": [{"field": "...", "message": "..."}, ...],
    "halt_reason": "brief-missing" | "brief-malformed" | "brief-invalid" | null,
    "brief": { ...parsed YAML if loadable, else null... }
  }

Exit codes:
  0 — valid (errors empty)
  1 — invalid (errors non-empty) OR file/yaml load failed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCHEMA_PATH = (
    REPO_ROOT / "src" / "shared" / "scripts" / "schemas" / "skill-brief.v1.json"
)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_schema() -> dict:
    """Read the skill-brief schema from its canonical path."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_brief_text(text: str) -> tuple[dict | None, str | None]:
    """Parse YAML text. Returns (brief, error_message)."""
    try:
        brief = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"Brief is not valid YAML: {exc}"
    if brief is None:
        return None, "Brief is empty"
    if not isinstance(brief, dict):
        return None, f"Brief must be a YAML mapping; got {type(brief).__name__}"
    return brief, None


# --------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------


def _field_path(error_path: tuple) -> str:
    """Render a jsonschema error path as `a.b[0].c`."""
    parts: list[str] = []
    for p in error_path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(f".{p}" if parts else str(p))
    return "".join(parts) or "(root)"


def _translate_jsonschema_error(err) -> dict:
    """Produce a skill-friendly error record from a jsonschema ValidationError."""
    field = _field_path(err.absolute_path)
    validator = err.validator
    inst = err.instance

    if validator == "required":
        missing = err.message.split("'")[1] if "'" in err.message else "(unknown)"
        return {
            "field": missing,
            "message": (
                f"Brief validation failed: missing required field `{missing}`. "
                f"Update your skill-brief.yaml and re-run."
            ),
        }
    if validator == "pattern":
        return {
            "field": field,
            "message": (
                f"Brief validation failed: `{field}` field `{inst}` does not "
                f"match required pattern `{err.validator_value}`. "
                f"Update your skill-brief.yaml and re-run."
            ),
        }
    if validator == "enum":
        return {
            "field": field,
            "message": (
                f"Brief validation failed: `{field}` field `{inst}` is not one of "
                f"{err.validator_value}. Update your skill-brief.yaml and re-run."
            ),
        }
    if validator == "type":
        expected = err.validator_value
        actual = type(inst).__name__
        return {
            "field": field,
            "message": (
                f"Brief validation failed: `{field}` field has type `{actual}`, "
                f"expected `{expected}`. Update your skill-brief.yaml and re-run."
            ),
        }
    if validator == "minLength":
        return {
            "field": field,
            "message": (
                f"Brief validation failed: `{field}` field must be non-empty. "
                f"Update your skill-brief.yaml and re-run."
            ),
        }
    if validator == "minItems":
        return {
            "field": field,
            "message": (
                f"Brief validation failed: `{field}` field must contain at least "
                f"{err.validator_value} item(s). Update your skill-brief.yaml and re-run."
            ),
        }
    # Fallback — preserve raw message but with consistent prefix
    return {
        "field": field,
        "message": f"Brief validation failed: `{field}` — {err.message}",
    }


# --------------------------------------------------------------------------
# Conditional rules from §3 prose
# --------------------------------------------------------------------------


def _docs_only_rules(brief: dict) -> tuple[list[dict], list[dict]]:
    """Apply the docs-only conditional rules.

    Returns (errors, warnings).
    """
    errors: list[dict] = []
    warnings: list[dict] = []
    if brief.get("source_type") != "docs-only":
        return errors, warnings

    doc_urls = brief.get("doc_urls")
    if not isinstance(doc_urls, list) or len(doc_urls) == 0:
        errors.append(
            {
                "field": "doc_urls",
                "message": (
                    "Brief validation failed: `doc_urls` must have at least one "
                    "entry when `source_type` is `docs-only`. "
                    "Update your skill-brief.yaml and re-run."
                ),
            }
        )

    source_authority = brief.get("source_authority")
    if source_authority not in (None, "community"):
        warnings.append(
            {
                "field": "source_authority",
                "message": (
                    f"`source_authority` is `{source_authority}` but will be treated "
                    f"as `community` because `source_type` is `docs-only`."
                ),
            }
        )
    return errors, warnings


def _version_non_empty_rule(brief: dict) -> list[dict]:
    """The §3 prose calls out version-whitespace-only as a hard error."""
    version = brief.get("version")
    if isinstance(version, str) and version.strip() == "" and version != "":
        # purely whitespace — schema's minLength check on patterns won't catch
        # leading/trailing whitespace that strips to empty
        return [
            {
                "field": "version",
                "message": (
                    "Brief validation failed: `version` field is required and "
                    "must be non-empty. Update your skill-brief.yaml and re-run."
                ),
            }
        ]
    return []


# --------------------------------------------------------------------------
# Main validate
# --------------------------------------------------------------------------


def validate_brief(brief: dict) -> dict:
    """Validate a parsed brief against the schema + conditional rules."""
    schema = load_schema()
    validator = Draft202012Validator(schema)

    errors: list[dict] = []
    warnings: list[dict] = []

    for err in sorted(validator.iter_errors(brief), key=lambda e: e.absolute_path):
        errors.append(_translate_jsonschema_error(err))

    cond_errors, cond_warnings = _docs_only_rules(brief)
    errors.extend(cond_errors)
    warnings.extend(cond_warnings)

    errors.extend(_version_non_empty_rule(brief))

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _emit(envelope: dict) -> None:
    json.dump(envelope, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _envelope_load_error(reason: str, message: str) -> dict:
    return {
        "valid": False,
        "errors": [{"field": "(file)", "message": message}],
        "warnings": [],
        "halt_reason": reason,
        "brief": None,
    }


def _envelope_invalid(brief: dict, errors: list[dict], warnings: list[dict]) -> dict:
    return {
        "valid": False,
        "errors": errors,
        "warnings": warnings,
        "halt_reason": "brief-invalid",
        "brief": brief,
    }


def _envelope_valid(brief: dict, warnings: list[dict]) -> dict:
    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "halt_reason": None,
        "brief": brief,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-validate-brief-schema",
        description="Validate a skill-brief.yaml against the SKF brief schema.",
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "path",
        nargs="?",
        help="path to skill-brief.yaml; pass `-` to read from stdin",
    )
    src.add_argument(
        "--yaml",
        dest="inline_yaml",
        help="inline YAML text to validate (alternative to a path)",
    )
    args = parser.parse_args(argv)

    if args.inline_yaml is not None:
        text = args.inline_yaml
    elif args.path == "-":
        text = sys.stdin.read()
    else:
        brief_path = Path(args.path)
        if not brief_path.is_file():
            _emit(
                _envelope_load_error(
                    "brief-missing",
                    f"Brief not found at `{brief_path}`. Run [BS] Brief Skill to "
                    "create one, or use [QS] Quick Skill for brief-less generation.",
                )
            )
            return 1
        text = brief_path.read_text(encoding="utf-8")

    brief, load_err = load_brief_text(text)
    if load_err is not None:
        _emit(_envelope_load_error("brief-malformed", load_err))
        return 1
    assert brief is not None

    result = validate_brief(brief)
    if not result["valid"]:
        _emit(_envelope_invalid(brief, result["errors"], result["warnings"]))
        return 1

    _emit(_envelope_valid(brief, result["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
