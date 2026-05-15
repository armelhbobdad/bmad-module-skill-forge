# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Write Skill Brief — Schema-validated atomic writer for skill-brief.yaml.

Replaces the prose-driven YAML emission, version-precedence resolution,
conditional optional-field rendering, and non-atomic file write currently
inlined in `src/skf-brief-skill/references/write-brief.md` §3-§4.

Each of those operations is purely deterministic: there is no LLM
judgement required to render the YAML, decide which optional fields
appear, resolve target_version vs. detected vs. default, or write the
file atomically. Keeping that work in prose creates four schema-drift
seams (key order, YAML formatting, conditional field inclusion rules,
atomic-write behaviour) that the LLM cannot fully close on every
invocation. This script is the single source of truth.

Subcommand:

  write   Read brief context as JSON on stdin, validate against
          src/shared/scripts/schemas/skill-brief.v1.json, apply
          version-precedence rules, render the canonical YAML, and
          atomically write to --target. Emits a JSON success envelope
          on stdout.

Context payload shape (consumed by `write`):

  {
    "name":             "marked",
    "version_resolved": "1.2.3",   # OR omit and provide:
    "target_version":   "1.2.3" | null,
    "detected_version": "1.2.3" | null,

    "source_type":      "source" | "docs-only",
    "source_repo":      "https://github.com/...",
    "language":         "javascript",
    "description":      "...",
    "forge_tier":       "Quick" | "Forge" | "Forge+" | "Deep",
    "created":          "2026-05-02",     # ISO date
    "created_by":       "armel",

    "scope": {
      "type":    "full-library" | ...,
      "include": ["src/**/*.ts"],
      "exclude": ["**/*.test.*"],
      "notes":   ""
    },

    # Conditionally present:
    "doc_urls":         [{"url": "...", "label": "..."}],
    "scripts_intent":   "detect" | "none" | free-text,
    "assets_intent":    "detect" | "none" | free-text,
    "source_authority": "official" | "community" | "internal"
  }

Version precedence (resolved into the rendered YAML's `version` field):
  1. version_resolved if explicitly supplied (caller already ran the
     precedence rule). Used by step 5 when it has confirmed values.
  2. Otherwise: target_version if non-null.
  3. Otherwise: detected_version if non-null.
  4. Otherwise: "1.0.0".

When target_version is set, the rendered YAML includes a `target_version`
field whose value MUST match `version` (the script enforces this
invariant before write — refuses to emit a brief that violates it).

Flat input form (`--from-flat`):

  Identical semantics, friendlier shape for prose-driven callers — scope
  is split across four top-level keys instead of nested, and every
  optional field can be passed as `null` without the caller deciding
  what to omit. The script translates flat → nested and runs the same
  validator + writer pipeline.

  {
    "name":             "marked",
    "target_version":   "1.2.3" | null,
    "detected_version": "1.2.3" | null,
    "source_type":      "source",
    "source_repo":      "https://github.com/...",
    "language":         "javascript",
    "description":      "...",
    "forge_tier":       "Quick",
    "created":          "2026-05-02",
    "created_by":       "armel",
    "scope_type":       "full-library",
    "scope_include":    ["src/**/*.ts"],
    "scope_exclude":    ["**/*.test.*"],
    "scope_notes":      "",
    "doc_urls":         null | [...],
    "scripts_intent":   null | "detect" | "none" | "...",
    "assets_intent":    null | "detect" | "none" | "...",
    "source_authority": null | "official" | "community" | "internal"
  }

Output (success):

  {
    "status":     "ok",
    "brief_path": "/abs/path/skill-brief.yaml",
    "version":    "<resolved version>",
    "bytes":      <integer>,
    "warnings":   ["string", ...]
  }

Errors emit `{"status": "error", "message": "...", "field": "..."|null}`
to stderr and exit non-zero.

Exit codes:
  0  — success
  1  — validation failure (bad context, schema violation, invariant
       violation, version-precedence underflow with no fallback path)
  2  — I/O failure (atomic write failed, parent directory not writable)

Cross-platform: pure stdlib + PyYAML. Atomic write via temp + fsync +
rename, mirroring skf-atomic-write.py and the helper in
skf-forge-tier-rw.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml


KEBAB_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
SEMVER_RE = re.compile(
    r"^v?\d+\.\d+\.\d+([.\-+][0-9A-Za-z][0-9A-Za-z.\-+]*)?$"
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_SOURCE_TYPES = {"source", "docs-only"}
VALID_SOURCE_AUTHORITIES = {"official", "community", "internal"}
VALID_FORGE_TIERS = {"Quick", "Forge", "Forge+", "Deep"}
VALID_SCOPE_TYPES = {
    "full-library",
    "specific-modules",
    "public-api",
    "component-library",
    "reference-app",
    "docs-only",
}


def _die(message: str, field: str | None = None, code: int = 1) -> None:
    payload = {"status": "error", "message": message}
    if field is not None:
        payload["field"] = field
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.exit(code)


def resolve_version(ctx: dict[str, Any]) -> str:
    """Apply the version-precedence rule. Returns the resolved version string.

    Uses `is not None` checks (not truthiness) so an explicitly-supplied
    empty string surfaces as a SEMVER_RE validation failure downstream
    rather than silently falling through to the next precedence level.
    """
    vr = ctx.get("version_resolved")
    if vr is not None:
        return vr
    tv = ctx.get("target_version")
    if tv is not None:
        return tv
    dv = ctx.get("detected_version")
    if dv is not None:
        return dv
    return "1.0.0"


def validate_context(ctx: dict[str, Any]) -> list[str]:
    """Validate the context payload. Raises via _die on hard errors; returns warnings."""
    warnings: list[str] = []

    # Required string fields
    for field in ("name", "source_repo", "language", "description",
                  "forge_tier", "created", "created_by"):
        v = ctx.get(field)
        if not v or not isinstance(v, str):
            _die(f"required field {field!r} missing or not a non-empty string", field=field)

    # Name must be kebab
    if not KEBAB_RE.match(ctx["name"]):
        _die(
            f"name must be kebab-case (lowercase letters/digits/hyphens, no leading/trailing hyphen). "
            f"Got: {ctx['name']!r}",
            field="name",
        )

    # forge_tier enum
    if ctx["forge_tier"] not in VALID_FORGE_TIERS:
        _die(
            f"forge_tier must be one of {sorted(VALID_FORGE_TIERS)}. Got: {ctx['forge_tier']!r}",
            field="forge_tier",
        )

    # created ISO date
    if not ISO_DATE_RE.match(ctx["created"]):
        _die(
            f"created must be an ISO date (YYYY-MM-DD). Got: {ctx['created']!r}",
            field="created",
        )

    # source_type (default 'source') and conditional doc_urls
    source_type = ctx.get("source_type", "source")
    if source_type not in VALID_SOURCE_TYPES:
        _die(
            f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}. Got: {source_type!r}",
            field="source_type",
        )

    doc_urls = ctx.get("doc_urls")
    if source_type == "docs-only":
        if not doc_urls or not isinstance(doc_urls, list) or len(doc_urls) == 0:
            _die("source_type=docs-only requires at least one entry in doc_urls", field="doc_urls")
    if doc_urls is not None:
        if not isinstance(doc_urls, list):
            _die("doc_urls must be an array of objects", field="doc_urls")
        for i, entry in enumerate(doc_urls):
            if not isinstance(entry, dict):
                _die(f"doc_urls[{i}] must be an object with at least a 'url' field", field="doc_urls")
            url = entry.get("url")
            if not url or not isinstance(url, str):
                _die(f"doc_urls[{i}].url is required and must be a non-empty string", field="doc_urls")

    # source_authority (default 'community') with docs-only force rule
    source_authority = ctx.get("source_authority", "community")
    if source_authority not in VALID_SOURCE_AUTHORITIES:
        _die(
            f"source_authority must be one of {sorted(VALID_SOURCE_AUTHORITIES)}. Got: {source_authority!r}",
            field="source_authority",
        )
    if source_type == "docs-only" and source_authority != "community":
        warnings.append(
            f"source_authority forced to 'community' for docs-only (was {source_authority!r})"
        )

    # scope object
    scope = ctx.get("scope")
    if not isinstance(scope, dict):
        _die("scope must be an object", field="scope")
    for sf in ("type", "include", "exclude", "notes"):
        if sf not in scope:
            _die(f"scope.{sf} is required", field=f"scope.{sf}")
    if scope["type"] not in VALID_SCOPE_TYPES:
        _die(
            f"scope.type must be one of {sorted(VALID_SCOPE_TYPES)}. Got: {scope['type']!r}",
            field="scope.type",
        )
    if not isinstance(scope["include"], list):
        _die("scope.include must be an array of glob strings", field="scope.include")
    if not isinstance(scope["exclude"], list):
        _die("scope.exclude must be an array of glob strings", field="scope.exclude")
    if not isinstance(scope["notes"], str):
        _die("scope.notes must be a string (use empty string when no notes)", field="scope.notes")

    # target_version semver shape (when present)
    tv = ctx.get("target_version")
    if tv is not None:
        if not isinstance(tv, str) or not SEMVER_RE.match(tv):
            _die(
                f"target_version must be full X.Y.Z semver (with optional v prefix and pre-release/build). "
                f"Got: {tv!r}",
                field="target_version",
            )

    detected = ctx.get("detected_version")
    if detected is not None and (not isinstance(detected, str) or not SEMVER_RE.match(detected)):
        # Warn rather than HALT — auto-detection upstream may surface odd shapes
        warnings.append(
            f"detected_version {detected!r} is not full X.Y.Z semver — falling through to default 1.0.0"
        )

    return warnings


def assemble_brief(ctx: dict[str, Any], resolved_version: str) -> dict[str, Any]:
    """Build the final brief dict that will be YAML-dumped, in canonical key order."""
    source_type = ctx.get("source_type", "source")
    source_authority = ctx.get("source_authority", "community")
    if source_type == "docs-only":
        source_authority = "community"  # forced

    brief: dict[str, Any] = {
        "name": ctx["name"],
        "version": resolved_version,
        "source_type": source_type,
        "source_repo": ctx["source_repo"],
        "language": ctx["language"],
        "description": ctx["description"],
        "forge_tier": ctx["forge_tier"],
        "created": ctx["created"],
        "created_by": ctx["created_by"],
        "scope": {
            "type": ctx["scope"]["type"],
            "include": list(ctx["scope"]["include"]),
            "exclude": list(ctx["scope"]["exclude"]),
            "notes": ctx["scope"]["notes"],
        },
    }

    # Conditional: target_version (must equal version)
    tv = ctx.get("target_version")
    if tv is not None:
        if tv != resolved_version:
            _die(
                f"invariant violation: target_version ({tv!r}) must equal version "
                f"({resolved_version!r}); see references/version-resolution.md",
                field="target_version",
            )
        brief["target_version"] = tv

    # Conditional: doc_urls (always emitted when present)
    doc_urls = ctx.get("doc_urls")
    if doc_urls:
        brief["doc_urls"] = [
            {"url": e["url"], "label": e.get("label", "")} for e in doc_urls
        ]

    # Conditional: scripts_intent / assets_intent — emit when explicitly non-detect
    for intent_field in ("scripts_intent", "assets_intent"):
        v = ctx.get(intent_field)
        if v is not None and v != "detect":
            brief[intent_field] = v

    # Emit source_authority only when non-default — schema lists it as Optional
    # in src/skf-brief-skill/assets/skill-brief-schema.md, and unconditional
    # emission would inject the field into round-tripped briefs that previously
    # omitted it (false-drift signal for diff tooling). Consumers default to
    # "community" when the field is absent.
    if source_authority != "community":
        brief["source_authority"] = source_authority

    return brief


def render_yaml(brief: dict[str, Any]) -> str:
    """Dump the brief dict as YAML in canonical key order with a leading document marker.

    The step 5 §3 template shows leading and trailing `---` markers, but those were
    wrapping the example YAML for documentation purposes — actual on-disk YAML uses
    only the leading `---` (or none). A trailing `---` would start a second empty
    document and break callers that use `yaml.safe_load` (which expects a single
    document) — and skf-create-skill / audit-skill / update-skill all use
    `yaml.safe_load`, so consistency with their loaders matters.
    """
    body = yaml.safe_dump(
        brief,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return "---\n" + body


def atomic_write(target: Path, content: str) -> int:
    """Crash-safe write via temp + fsync + rename. Returns bytes written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".skf-tmp")
    encoded = content.encode("utf-8")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, encoded)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except OSError as e:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        _die(f"atomic write failed for {target}: {e}", code=2)
    return len(encoded)


# Top-level keys that get folded into the nested `scope` sub-object — every
# other top-level key passes through unchanged so future additions to the
# schema don't require a translator update.
_FLAT_SCOPE_KEYS = ("scope_type", "scope_include", "scope_exclude", "scope_notes")


def flat_to_nested(flat: dict[str, Any]) -> dict[str, Any]:
    """Translate the flat brief-context shape into the nested shape consumed by validate_context.

    Flat shape: scope is split across four top-level keys (`scope_type`,
    `scope_include`, `scope_exclude`, `scope_notes`) instead of nested
    under a `scope` object. Optional top-level fields (`doc_urls`,
    `scripts_intent`, `assets_intent`, `source_authority`,
    `target_version`, `detected_version`) may be absent or null —
    they are simply dropped from the nested output, which matches the
    existing validator's `ctx.get(...) is None` semantics.

    Any unknown top-level keys are passed through unchanged so future
    additions don't require a translator update.
    """
    if not isinstance(flat, dict):
        _die("write --from-flat: payload must be a JSON object")

    nested: dict[str, Any] = {}

    # Pass through every top-level key that isn't part of the flat-scope
    # split. Drop None values so optional fields behave as "absent" in
    # the nested form (validate_context uses `is not None` checks).
    for key, value in flat.items():
        if key in _FLAT_SCOPE_KEYS:
            continue
        if value is None:
            continue
        nested[key] = value

    # Build the nested scope object. All four scope_* keys (type, include,
    # exclude, notes) are required at the schema level — null is
    # intentionally treated as "absent" here (same as omitting the key)
    # so validate_context surfaces `scope.<field> is required` rather
    # than e.g. `scope.notes must be a string`. The `""` valid minimum
    # for scope_notes must therefore be passed as the literal empty
    # string, not null.
    if any(k in flat for k in _FLAT_SCOPE_KEYS):
        scope: dict[str, Any] = {}
        if "scope_type" in flat and flat["scope_type"] is not None:
            scope["type"] = flat["scope_type"]
        if "scope_include" in flat and flat["scope_include"] is not None:
            scope["include"] = flat["scope_include"]
        if "scope_exclude" in flat and flat["scope_exclude"] is not None:
            scope["exclude"] = flat["scope_exclude"]
        if "scope_notes" in flat and flat["scope_notes"] is not None:
            scope["notes"] = flat["scope_notes"]
        nested["scope"] = scope
    return nested


def cmd_write(target: Path, from_flat: bool = False) -> int:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        _die("write: empty stdin (expected JSON brief context)")
    try:
        ctx = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"write: invalid JSON on stdin: {e}")
    if not isinstance(ctx, dict):
        _die("write: context payload must be a JSON object")

    if from_flat:
        ctx = flat_to_nested(ctx)

    warnings = validate_context(ctx)
    resolved_version = resolve_version(ctx)
    if not SEMVER_RE.match(resolved_version):
        _die(
            f"resolved version {resolved_version!r} is not full X.Y.Z semver — "
            f"check version_resolved / target_version / detected_version inputs",
            field="version",
        )

    brief = assemble_brief(ctx, resolved_version)
    content = render_yaml(brief)
    bytes_written = atomic_write(target, content)

    response = {
        "status": "ok",
        "brief_path": str(target.resolve()),
        "version": resolved_version,
        "bytes": bytes_written,
        "warnings": warnings,
    }
    print(json.dumps(response))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skf-write-skill-brief",
        description="Schema-validated atomic writer for skill-brief.yaml.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_write = sub.add_parser("write", help="Read brief context JSON on stdin, validate, render YAML, atomic write")
    p_write.add_argument("--target", type=Path, required=True, help="Absolute path to skill-brief.yaml")
    p_write.add_argument(
        "--from-flat",
        action="store_true",
        help=(
            "Accept the flat brief-context shape (scope split across "
            "scope_type/scope_include/scope_exclude/scope_notes top-level keys, "
            "optional fields nullable) instead of the nested shape. Eliminates "
            "the conditional-omit logic the LLM currently walks at the §3 "
            "assembly site in step 5."
        ),
    )

    args = parser.parse_args()
    if args.cmd == "write":
        return cmd_write(args.target, from_flat=args.from_flat)
    return 2


if __name__ == "__main__":
    sys.exit(main())
