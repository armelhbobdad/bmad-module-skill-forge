# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Validate Brief Inputs — pre-pass validation for brief-skill headless invocation.

Validates and normalizes the headless argument set passed to skf-brief-skill
before the workflow's interactive sequence runs. Catches malformed inputs at
point of capture instead of letting them surface 5+ minutes later in step-02
or step-05.

CLI:
  uv run skf-validate-brief-inputs.py --json '{...}'
  echo '{...}' | uv run skf-validate-brief-inputs.py

Input (JSON object on stdin or via --json):
  Required:
    target_repo  — string (URL or path); error if absent
    skill_name   — string (kebab-case); error if absent or malformed

  Optional with enum constraints:
    source_type      — "source" | "docs-only" (default "source")
    source_authority — "official" | "community" | "internal" (default "community")
    scope_type       — "full-library" | "specific-modules" | "public-api"
                       | "component-library" | "reference-app" | "docs-only"
    scripts_intent   — "detect" | "none" | free-text (default "detect")
    assets_intent    — "detect" | "none" | free-text (default "detect")

  Optional with format constraints:
    target_version — loose semver string (matches 1.2.3, 1.2.3-rc.1, 1.2.3+build.5)

  Conditional:
    doc_urls — required when source_type == "docs-only"

  Free-text / pass-through:
    scope_hint, language_hint, intent, include, exclude, force

  Unrecognized keys are passed through unchanged but flagged as warnings.

Output (JSON on stdout):
  {
    "valid": bool,
    "errors":   [{"field": "...", "message": "..."}, ...],
    "warnings": [{"field": "...", "message": "..."}, ...],
    "normalized": { ...input dict with defaults applied... },
    "halt_reason": "input-missing" | "input-invalid" | null
  }

Exit codes:
  0 — valid (errors empty)
  1 — invalid (errors present); halt_reason is set
  2 — internal error (bad JSON input, IO failure)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

KNOWN_FIELDS = {
    "target_repo",
    "skill_name",
    "source_type",
    "source_authority",
    "scope_type",
    "target_version",
    "doc_urls",
    "scope_hint",
    "language_hint",
    "intent",
    "scripts_intent",
    "assets_intent",
    "include",
    "exclude",
    "force",
}
# `preset` is intentionally NOT in KNOWN_FIELDS — it is consumed at the step-01 §8 GATE
# (the LLM merges the named preset YAML into the args dict and drops the `preset` key
# before calling the validator). If the key leaks through, the validator's existing
# unknown-field handling emits `"unrecognized field 'preset' — passed through unchanged"`
# in `warnings[]` so the missed drop is debuggable rather than silent.

VALID_SOURCE_TYPES = {"source", "docs-only"}
VALID_SOURCE_AUTHORITIES = {"official", "community", "internal"}
VALID_SCOPE_TYPES = {
    "full-library",
    "specific-modules",
    "public-api",
    "component-library",
    "reference-app",
    "docs-only",
}

KEBAB_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
# Require full X.Y.Z form (with optional v prefix and pre-release/build suffix).
# Loose forms like `1`, `1.2`, `v2` are rejected — the user should write the
# explicit triple. CalVer (e.g. 2024.04.01) is accepted because it satisfies
# the X.Y.Z shape.
SEMVER_RE = re.compile(
    r"^v?\d+\.\d+\.\d+([.\-+][0-9A-Za-z][0-9A-Za-z.\-+]*)?$"
)
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _err(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def validate(inp: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    # Required: target_repo, skill_name
    target_repo = inp.get("target_repo")
    skill_name = inp.get("skill_name")
    if not target_repo:
        errors.append(_err("target_repo", "missing required argument target_repo"))
    if not skill_name:
        errors.append(_err("skill_name", "missing required argument skill_name"))

    # skill_name format
    if skill_name and isinstance(skill_name, str) and not KEBAB_RE.match(skill_name):
        errors.append(
            _err(
                "skill_name",
                f"skill_name must be kebab-case (lowercase letters/digits/hyphens, "
                f"no leading or trailing hyphen). Got: {skill_name!r}",
            )
        )

    # source_type enum
    source_type_raw = inp.get("source_type", "source")
    if source_type_raw not in VALID_SOURCE_TYPES:
        errors.append(
            _err(
                "source_type",
                f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}. Got: {source_type_raw!r}",
            )
        )
        # Treat as default for downstream conditional logic
        source_type = "source"
    else:
        source_type = source_type_raw

    # source_authority enum
    source_authority_raw = inp.get("source_authority", "community")
    if source_authority_raw not in VALID_SOURCE_AUTHORITIES:
        errors.append(
            _err(
                "source_authority",
                f"source_authority must be one of {sorted(VALID_SOURCE_AUTHORITIES)}. "
                f"Got: {source_authority_raw!r}",
            )
        )

    # scope_type enum (when present)
    scope_type = inp.get("scope_type")
    if scope_type is not None and scope_type not in VALID_SCOPE_TYPES:
        errors.append(
            _err(
                "scope_type",
                f"scope_type must be one of {sorted(VALID_SCOPE_TYPES)}. Got: {scope_type!r}",
            )
        )

    # target_version semver-ish
    target_version = inp.get("target_version")
    if target_version is not None:
        if not isinstance(target_version, str):
            errors.append(
                _err(
                    "target_version",
                    f"target_version must be a string. Got type {type(target_version).__name__}",
                )
            )
        elif not SEMVER_RE.match(target_version):
            errors.append(
                _err(
                    "target_version",
                    f"target_version does not look like semver. Got: {target_version!r}. "
                    f"Expected forms: 1.2.3, v1.2.3, 1.2.3-rc.1, 1.2.3+build.5. "
                    f"Partial forms like '1' or '1.2' are not accepted — write the explicit triple.",
                )
            )

    # docs-only requires doc_urls
    doc_urls = inp.get("doc_urls")
    if source_type == "docs-only" and not doc_urls:
        errors.append(
            _err("doc_urls", "doc_urls is required when source_type is docs-only")
        )

    # target_repo shape (warning only — script doesn't HEAD-check)
    if isinstance(target_repo, str) and target_repo:
        looks_like_url = URL_RE.match(target_repo) is not None
        looks_like_path = (
            target_repo.startswith("/")
            or target_repo.startswith("./")
            or target_repo.startswith("~")
        )
        if not (looks_like_url or looks_like_path):
            warnings.append(
                _err(
                    "target_repo",
                    f"target_repo does not look like a URL or absolute/relative path: {target_repo!r}",
                )
            )

    # Unknown fields → warn
    for key in inp:
        if key not in KNOWN_FIELDS:
            warnings.append(_err(key, f"unrecognized field {key!r} — passed through unchanged"))

    # Build normalized payload
    normalized: dict[str, Any] = dict(inp)
    normalized.setdefault("source_type", "source")
    # `source_authority` is intentionally NOT setdefault'd here for source-type targets:
    # step-01 §3.3's headless detection branch runs `gh api user` and may resolve to
    # `official` for repos owned by the authenticated user. Stamping a default at
    # validator time would pre-empt the detection because step-01 §8 GATE treats the
    # `normalized` object as the source of truth. Absence is the signal "run detection."
    # The docs-only branch below still forces `community` since detection cannot apply.
    normalized.setdefault("scripts_intent", "detect")
    normalized.setdefault("assets_intent", "detect")

    # Force community when docs-only
    if normalized.get("source_type") == "docs-only":
        if normalized.get("source_authority") not in (None, "community"):
            warnings.append(
                _err(
                    "source_authority",
                    f"source_authority forced to 'community' because source_type=docs-only "
                    f"(was {normalized['source_authority']!r})",
                )
            )
        normalized["source_authority"] = "community"

    # halt_reason classification
    if errors:
        missing_required = any(
            e["message"].startswith("missing required") or "is required" in e["message"]
            for e in errors
        )
        halt_reason = "input-missing" if missing_required else "input-invalid"
    else:
        halt_reason = None

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized,
        "halt_reason": halt_reason,
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="skf-validate-brief-inputs")
    p.add_argument(
        "--json",
        help="JSON object as a string. If omitted, the script reads JSON from stdin.",
    )
    args = p.parse_args()

    raw = args.json
    if raw is None:
        raw = sys.stdin.read()

    if not raw or not raw.strip():
        sys.stderr.write("skf-validate-brief-inputs: empty input\n")
        return 2

    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"skf-validate-brief-inputs: invalid JSON input: {e}\n")
        return 2

    if not isinstance(inp, dict):
        sys.stderr.write("skf-validate-brief-inputs: input must be a JSON object\n")
        return 2

    result = validate(inp)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
