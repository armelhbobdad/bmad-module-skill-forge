# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema>=4.0"]
# ///
"""SKF Validate Brief Schema — schema check for a skill-brief.yaml on disk.

Loads `skill-brief.yaml` from a path (or from stdin/inline-YAML), validates
it against `schemas/skill-brief.v1.json` (sibling of this script), and applies the
conditional rules from `skf-create-skill/references/load-brief.md §3`
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
  - `scope.include` must contain ≥1 glob pattern for every scope type except
    `docs-only`. The schema requires the `scope.include` key but types it as
    an array without a `minItems` floor; this rule enforces the non-empty
    constraint conditional on `scope.type`, matching brief-skill's
    consumption-time validation.

The script produces skill-friendly error messages — translating raw
jsonschema diagnostics into the "Brief validation failed: ..." form the
calling stage prose already uses. Calling stages can read `errors[]`
directly and forward the `message` field to the user.

CLI:
  uv run skf-validate-brief-schema.py <path/to/skill-brief.yaml>
  cat brief.yaml | uv run skf-validate-brief-schema.py -
  uv run skf-validate-brief-schema.py --yaml '<inline yaml>'
  uv run skf-validate-brief-schema.py batch --contexts FILE [FILE ...]
      [--existing-skills [NAME ...]] [--project-paths [PATH ...]]
      [--scan-roots [ROOT ...]]

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

`batch` checks the brief contexts (the flat JSON skf-write-skill-brief.py
--from-flat reads) of one Analyze Source run together, for what no single
brief shows. In context order, each context's:

  - `name`, when it is a non-empty string, must not be the name of an
    earlier context (the error names both files) or one of
    --existing-skills (a compiled skill: rename the unit, or run
    update-skill on that skill);
  - `source_repo`, when it is a non-empty string, must be an existing
    folder (a leading `~` expanded), or a --project-paths entry whose
    --scan-roots entry (the two lists pair by position) is an existing
    folder: a remote project path is reachable through the scan root the
    run cloned it into.

A value that is absent or no string is left to the schema check of each
brief. A --contexts value that is no file and holds `*` or `?` is expanded
here (sorted), its file name the pattern and its folder read as written,
so the call works where no shell expands it. Its output:

  {"valid": bool,
   "errors": [{"context": "<file>", "name": "<brief name>", "field": "name" | "source_repo",
               "message": "Brief validation failed: ..."}, ...],
   "warnings": []}

and it exits 0 when valid, 1 with errors, and 2 on a usage error, named
on stderr with nothing on stdout: lists of different lengths, a context
that cannot be read or is no JSON object, or a pattern that matches no
file.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "skill-brief.v1.json"
RESOLVER_PATH = Path(__file__).resolve().parent / "skf-resolve-authoritative-files.py"


def _load_resolver():
    """skf-resolve-authoritative-files.py from this folder: its
    parse_brief_yaml reads a brief's YAML, an SKF 1.x brief's trailing `---`
    included. A missing file raises OSError, which skf-quick-batch.py
    reports as a validator that cannot be loaded."""
    spec = importlib.util.spec_from_file_location("skf_resolve_authoritative_files", RESOLVER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {RESOLVER_PATH.name} beside {Path(__file__).name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RESOLVER = _load_resolver()


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_schema() -> dict:
    """Read the skill-brief schema from its canonical path."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_brief_text(text: str) -> tuple[dict | None, str | None]:
    """Parse YAML text. Returns (brief, error_message)."""
    try:
        brief = _RESOLVER.parse_brief_yaml(text)
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
        if err.absolute_path:
            # A nested object's field (`scope.ui_variants[0].name`), not a top-level one.
            missing = f"{field}.{missing}"
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
        # A bare YAML date/datetime scalar (e.g. `created: 2026-05-01` without
        # quotes) parses as a Python date, not a string. Give an actionable
        # "quote it" hint instead of the opaque "has type `date`" message.
        if isinstance(inst, datetime.date) and err.validator_value == "string":
            return {
                "field": field,
                "message": (
                    f"Brief validation failed: `{field}` was parsed as a YAML date, "
                    f"not a string. Quote it (e.g. `'2026-05-01'`) so it is stored as "
                    f"text. Update your skill-brief.yaml and re-run."
                ),
            }
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


def _target_version_matches_version_rule(brief: dict) -> list[dict]:
    """`target_version`, when present, must equal `version` (writer invariant).

    The JSON schema constrains both fields to the semver pattern independently
    but cannot express their cross-field equality. Without this check, a brief
    with mismatched `target_version`/`version` passes schema validation (the
    ratify gate) and only fails later at the writer's `assemble_brief`
    invariant. Surfacing it here turns that into a clean `brief-invalid` at the
    validation step. Non-string values are left to the schema's pattern/type
    rules — we only compare when both are strings.
    """
    tv = brief.get("target_version")
    v = brief.get("version")
    if isinstance(tv, str) and isinstance(v, str) and tv != v:
        return [
            {
                "field": "target_version",
                "message": (
                    f"Brief validation failed: `target_version` (`{tv}`) must equal "
                    f"`version` (`{v}`). When `target_version` is set it becomes the "
                    f"skill's version. Update your skill-brief.yaml and re-run."
                ),
            }
        ]
    return []


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


def _scope_include_non_empty_rule(brief: dict) -> list[dict]:
    """`scope.include` must carry ≥1 glob pattern, except for docs-only scope.

    The JSON schema requires the `scope.include` key and types it as an array of
    strings, but cannot express the non-empty constraint conditional on
    `scope.type`. A `docs-only` skill has no source globs to include, so it is
    exempt; every other scope type must name at least one pattern or the
    downstream extraction has nothing to walk. Surfacing it here keeps the
    deterministic gate consistent with brief-skill's consumption-time
    validation instead of paying the model to re-check structure each run.
    """
    scope = brief.get("scope")
    if not isinstance(scope, dict):
        # missing/malformed scope is the schema's `required`/`type` job
        return []
    if scope.get("type") == "docs-only":
        return []
    include = scope.get("include")
    if not (isinstance(include, list) and len(include) >= 1):
        return [
            {
                "field": "scope.include",
                "message": (
                    "Brief validation failed: `scope.include` must contain at "
                    "least one glob pattern (docs-only scope excepted). "
                    "Update your skill-brief.yaml and re-run."
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
    errors.extend(_target_version_matches_version_rule(brief))
    errors.extend(_scope_include_non_empty_rule(brief))

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _emit(envelope: dict) -> None:
    # default=str keeps the echoed `brief` serializable even when it contains
    # non-JSON scalars (e.g. a YAML date object from an unquoted `created:`
    # field). Without it, emitting the invalid-brief envelope would crash with
    # `TypeError: Object of type date is not JSON serializable` instead of
    # returning the graded brief-invalid result.
    json.dump(envelope, sys.stdout, indent=2, default=str)
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


# --------------------------------------------------------------------------
# batch: the checks across one run's brief contexts
# --------------------------------------------------------------------------


class BatchUsageError(Exception):
    """A batch call that cannot be checked: exit 2, the message on stderr."""


def _expand_contexts(values: list[str]) -> list[Path]:
    """Each --contexts value as a path, a pattern no shell expanded expanded here (sorted)."""
    paths: list[Path] = []
    for value in values:
        if not Path(value).is_file() and any(ch in value for ch in "*?"):
            folder, pattern = os.path.split(value)  # a folder holding [ ] * ? is no pattern
            matches = sorted(glob.glob(os.path.join(glob.escape(folder), pattern)))
            if not matches:
                raise BatchUsageError(f"--contexts pattern `{value}` matches no file")
            paths.extend(Path(m) for m in matches)
        else:
            paths.append(Path(value))
    return paths


def _read_context(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise BatchUsageError(f"context `{path}` cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BatchUsageError(f"context `{path}` is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BatchUsageError(f"context `{path}` is not a JSON object")
    return data


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_folder(value: str) -> bool:
    try:
        return Path(value).expanduser().is_dir()
    except (OSError, RuntimeError, ValueError):  # RuntimeError: a `~user` with no home
        return False


def check_batch(contexts: list[tuple[str, dict]], existing_skills: list[str],
                project_paths: list[str], scan_roots: list[str]) -> dict:
    """The batch checks over (file, context) pairs, in order. Raises
    BatchUsageError when the two path lists differ in length."""
    if len(project_paths) != len(scan_roots):
        raise BatchUsageError(
            f"--project-paths gives {len(project_paths)} path(s) and --scan-roots {len(scan_roots)}: "
            "give one scan root per project path, in the same order")
    roots: dict[str, list[str]] = {}
    for path, root in zip(project_paths, scan_roots):
        roots.setdefault(path, []).append(root)
    reachable = {path for path, listed in roots.items() if any(_is_folder(root) for root in listed)}
    existing = set(existing_skills)
    seen: dict[str, str] = {}
    errors: list[dict] = []

    def error(context: str, name: Any, field: str, message: str) -> None:
        errors.append({"context": context, "name": name if isinstance(name, str) else None,
                       "field": field, "message": f"Brief validation failed: {message}"})

    for context, data in contexts:
        name = data.get("name")
        if _non_empty(name):
            if name in existing:
                error(context, name, "name",
                      f"`name` `{name}` in `{context}` is the name of an existing skill. Rename the unit, "
                      f"or run update-skill on that skill.")
            elif name in seen:
                error(context, name, "name",
                      f"`name` `{name}` in `{context}` is also the name of the brief in `{seen[name]}`. "
                      f"Rename one of the two units and re-run.")
            seen.setdefault(name, context)
        source = data.get("source_repo")
        if _non_empty(source) and not _is_folder(source) and source not in reachable:
            if source in roots:
                listed = ", ".join(f"`{root}`" for root in roots[source])
                message = (f"`source_repo` `{source}` in `{context}` is a project path whose scan root "
                           f"{listed} is not an existing folder. Restore that folder, or make the scan root "
                           f"again from the project path, and re-run.")
            else:
                message = (f"`source_repo` `{source}` in `{context}` is neither an existing folder nor a "
                           f"project path of this run. Set it to the unit's project path and re-run.")
            error(context, name, "source_repo", message)
    return {"valid": not errors, "errors": errors, "warnings": []}


def _batch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-validate-brief-schema batch",
        description="Check one run's brief contexts together: names shared with another brief or an "
                    "existing skill, and a source_repo that is neither an existing folder nor a project "
                    "path whose scan root exists.",
    )
    parser.add_argument("--contexts", nargs="+", required=True, metavar="FILE",
                        help="the brief context JSON files; a pattern no shell expanded is expanded here")
    parser.add_argument("--existing-skills", nargs="*", default=[], metavar="NAME",
                        help="the names of the skills that already exist")
    parser.add_argument("--project-paths", nargs="*", default=[], metavar="PATH",
                        help="the run's project paths, in order")
    parser.add_argument("--scan-roots", nargs="*", default=[], metavar="ROOT",
                        help="the scan root of each --project-paths entry, in the same order")
    return parser


def batch_main(argv: list[str]) -> int:
    args = _batch_parser().parse_args(argv)
    try:
        paths = _expand_contexts(args.contexts)
        contexts = [(str(path), _read_context(path)) for path in paths]
        result = check_batch(contexts, args.existing_skills, args.project_paths, args.scan_roots)
    except BatchUsageError as exc:
        sys.stderr.write(f"skf-validate-brief-schema batch: {exc}\n")
        return 2
    _emit(result)
    return 0 if result["valid"] else 1


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["batch"]:
        return batch_main(argv[1:])
    parser = argparse.ArgumentParser(
        prog="skf-validate-brief-schema",
        description="Validate a skill-brief.yaml against the SKF brief schema.",
        epilog="`skf-validate-brief-schema.py batch --contexts FILE ...` checks one Analyze Source run's brief "
               "contexts together instead; `batch --help` lists its options.",
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
