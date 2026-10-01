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

Subcommands:

  write   Read brief context as JSON on stdin, validate against
          src/shared/scripts/schemas/skill-brief.v1.json, apply
          version-precedence rules, render the canonical YAML, and
          atomically write to --target. Emits a JSON success envelope
          on stdout. With --base-brief, the context is a brief already
          on disk instead, with the changes the other two flags give
          (see "Base brief form" below).

  amend   Read answers as JSON on stdin and apply them to the brief
          already at --target: set scope.registry_path and
          scope.demo_patterns, append the entries to scope.amendments,
          check those fields as write does, copy the brief to
          <target>.bak, and write it atomically. Every other field keeps
          its value and its place; comments are not kept (the .bak copy
          holds them). create-skill step 3d records its answers so.

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
      "notes":   "",
      # Conditionally present (preserved verbatim on a ratify/re-write):
      "tier_a_include": ["code/core/src/**"],   # stratified-scope monorepos
      "amendments":     [{...}],                # post-authoring audit log
      # component-library scopes (create-skill step 3d writes the first
      # two back when the user confirms them):
      "registry_path":  "registry/index.ts",
      "ui_variants":    [{"name": "shadcnui", "package": "packages/ui"}],
      "demo_patterns":  ["**/demo/**", "**/*.stories.*"]
    },

    # Conditionally present:
    "doc_urls":         [{"url": "...", "label": "...", "source": "..."}],
    #   `source` (optional per #432): language-registry | readme-detection |
    #   homepage | pages-api | docs-folder. Threaded through when present;
    #   absent → entry renders as {url, label} only (no false drift).
    "scripts_intent":   "detect" | "none" | free-text,
    "assets_intent":    "detect" | "none" | free-text,
    "source_authority": "official" | "community" | "internal",
    "target_ref":       "livekit/v0.7.42",   # monorepo tag escape hatch
    "source_ref":       "v0.5.0"             # auto-resolved git ref
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
    "scope_type":           "full-library",
    "scope_include":        ["src/**/*.ts"],
    "scope_exclude":        ["**/*.test.*"],
    "scope_notes":          "",
    "scope_tier_a_include": null | ["code/core/src/**"],
    "scope_amendments":     null | [{...}],
    "scope_registry_path":  null | "registry/index.ts",
    "scope_ui_variants":    null | [{"name": "...", "package": "..."}],
    "scope_demo_patterns":  null | ["**/demo/**"],
    "doc_urls":             null | [{"url": "...", "label": "...", "source": "..."}],
    "scripts_intent":       null | "detect" | "none" | "...",
    "assets_intent":        null | "detect" | "none" | "...",
    "source_authority":     null | "official" | "community" | "internal",
    "target_ref":           null | "livekit/v0.7.42",
    "source_ref":           null | "v0.5.0"
  }

Base brief form (`write --base-brief <file> [--doc-urls-file <file>]
[--patch-file <file>]`):

  The context is the brief in --base-brief (a skill-brief.yaml), so a
  caller that rewrites a brief never retypes it and no field it holds is
  dropped. --doc-urls-file replaces its doc_urls with the `doc_urls` of
  that file (the output of skf-merge-doc-urls.py). --patch-file lays a
  JSON object of changes over it: an object merges key by key, null
  removes the key, and any other value (a string, a list) replaces it.
  version_resolved is the patch's version_resolved, else the result's
  `version`, so the version the brief holds (or the one the patch sets)
  is written; a brief with a target_version needs the patch to change
  both. stdin is not read, and --from-flat does not apply. A date the
  YAML holds unquoted is read as its ISO text.

Output (success):

  {
    "status":     "ok",
    "brief_path": "/abs/path/skill-brief.yaml",
    "version":    "<resolved version>",
    "bytes":      <integer>,
    "warnings":   ["string", ...]
  }

Answers payload (consumed by `amend`), each key optional, one at least:

  {
    "registry_path": "registry/index.ts",
    "demo_patterns": ["**/examples/**"],
    "amendments":    [{"path": "...", "action": "...", "category": "...",
                       "reason": "...", "evidence": "...",
                       "date": "2026-10-01", "workflow": "..."}]
  }

  Each amendment needs a non-empty path, action, reason and workflow and
  an ISO date; category, when given, is a non-empty string.

Output of `amend` (success):

  {
    "status":     "ok",
    "brief_path": "/abs/path/skill-brief.yaml",
    "backup":     "/abs/path/skill-brief.yaml.bak",
    "set":        ["registry_path", "demo_patterns"],   # the fields given
    "appended":   <integer>,                            # amendment entries
    "bytes":      <integer>
  }

Errors emit `{"status": "error", "message": "...", "field": "..."|null}`
to stderr and exit non-zero.

Exit codes:
  0  — success
  1  — validation failure (bad context, schema violation, invariant
       violation, version-precedence underflow with no fallback path)
       or, for amend, a bad payload or a brief with no scope mapping
  2  — I/O failure (atomic write failed, parent directory not writable)
       or, for amend, a brief that cannot be read or a backup that
       cannot be written

Cross-platform: pure stdlib + PyYAML. Atomic write via temp + fsync +
rename, mirroring skf-atomic-write.py and the helper in
skf-forge-tier-rw.py.
"""

from __future__ import annotations

import argparse
import datetime
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

    # scope.rationale — optional authoring-time scope-type decision record.
    # Absent/None → field is simply not present (same null-drop path as
    # doc_urls). When present it must be a complete six-subkey object.
    rationale = scope.get("rationale")
    if rationale is not None:
        if not isinstance(rationale, dict):
            _die("scope.rationale must be an object when present", field="scope.rationale")
        _RATIONALE_STR_KEYS = ("recommended", "chosen", "heuristic", "reason", "recorded")
        for rk in (*_RATIONALE_STR_KEYS, "accepted_recommendation"):
            if rk not in rationale:
                _die(f"scope.rationale.{rk} is required", field=f"scope.rationale.{rk}")
        for rk in _RATIONALE_STR_KEYS:
            if not isinstance(rationale[rk], str) or not rationale[rk]:
                _die(
                    f"scope.rationale.{rk} must be a non-empty string",
                    field=f"scope.rationale.{rk}",
                )
        if not isinstance(rationale["accepted_recommendation"], bool):
            _die(
                "scope.rationale.accepted_recommendation must be a boolean",
                field="scope.rationale.accepted_recommendation",
            )
        for rk in ("recommended", "chosen"):
            if rationale[rk] not in VALID_SCOPE_TYPES:
                _die(
                    f"scope.rationale.{rk} must be one of {sorted(VALID_SCOPE_TYPES)}. "
                    f"Got: {rationale[rk]!r}",
                    field=f"scope.rationale.{rk}",
                )

    # scope.tier_a_include — optional narrower tier-A include list for
    # stratified-scope monorepos (read by skf-test-skill for the coverage
    # denominator). Absent/None → key omitted. When present it must be a list
    # of glob strings; the writer preserves it verbatim so a ratify/re-write
    # does not silently drop it.
    tier_a_include = scope.get("tier_a_include")
    if tier_a_include is not None:
        if not isinstance(tier_a_include, list):
            _die("scope.tier_a_include must be an array of glob strings", field="scope.tier_a_include")
        for i, pat in enumerate(tier_a_include):
            if not isinstance(pat, str) or not pat:
                _die(
                    f"scope.tier_a_include[{i}] must be a non-empty glob string",
                    field="scope.tier_a_include",
                )

    # scope.amendments — optional additive audit log written post-authoring by
    # skf-create-skill / skf-update-skill. The writer is not the amendments
    # schema authority (those workflows own the entry shape); it only preserves
    # the log verbatim on re-write. Light check: a list of objects.
    amendments = scope.get("amendments")
    if amendments is not None:
        if not isinstance(amendments, list):
            _die("scope.amendments must be an array of amendment objects", field="scope.amendments")
        for i, entry in enumerate(amendments):
            if not isinstance(entry, dict):
                _die(f"scope.amendments[{i}] must be an object", field="scope.amendments")

    _check_component_fields(scope)

    # target_ref / source_ref — optional git refs (top-level). target_ref is a
    # remote-monorepo tag escape hatch; source_ref is the auto-resolved ref.
    # Both must round-trip on a ratify/re-write rather than being dropped.
    for ref_field in ("target_ref", "source_ref"):
        ref_val = ctx.get(ref_field)
        if ref_val is not None and (not isinstance(ref_val, str) or not ref_val):
            _die(f"{ref_field} must be a non-empty string when present", field=ref_field)

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


def _check_component_fields(scope: dict[str, Any]) -> None:
    """scope.registry_path / scope.ui_variants / scope.demo_patterns: optional
    component-library fields. A brief can author them, and create-skill
    step 3d writes a confirmed registry path and demo patterns back (amend),
    so a ratify/re-write preserves them verbatim. Light checks mirror the
    schema."""
    registry_path = scope.get("registry_path")
    if registry_path is not None and (not isinstance(registry_path, str) or not registry_path):
        _die("scope.registry_path must be a non-empty string when present", field="scope.registry_path")
    demo_patterns = scope.get("demo_patterns")
    if demo_patterns is not None:
        if not isinstance(demo_patterns, list):
            _die("scope.demo_patterns must be an array of glob strings", field="scope.demo_patterns")
        for i, pat in enumerate(demo_patterns):
            if not isinstance(pat, str) or not pat:
                _die(f"scope.demo_patterns[{i}] must be a non-empty glob string", field="scope.demo_patterns")
    ui_variants = scope.get("ui_variants")
    if ui_variants is not None:
        if not isinstance(ui_variants, list):
            _die("scope.ui_variants must be an array of variant objects", field="scope.ui_variants")
        for i, variant in enumerate(ui_variants):
            if not isinstance(variant, dict):
                _die(f"scope.ui_variants[{i}] must be an object", field="scope.ui_variants")
            for key in ("name", "package"):
                value = variant.get(key)
                if value is not None and (not isinstance(value, str) or not value):
                    _die(f"scope.ui_variants[{i}].{key} must be a non-empty string when present",
                         field="scope.ui_variants")


def assemble_brief(ctx: dict[str, Any], resolved_version: str) -> dict[str, Any]:
    """Build the final brief dict that will be YAML-dumped, in canonical key order."""
    source_type = ctx.get("source_type", "source")
    source_authority = ctx.get("source_authority", "community")
    if source_type == "docs-only":
        source_authority = "community"  # forced

    # Build the scope sub-object. tier_a_include (when present) sits between
    # exclude and notes, matching the schema doc's illustrative order. Absent →
    # the key is omitted, so briefs without it render byte-identically to before.
    scope_obj: dict[str, Any] = {
        "type": ctx["scope"]["type"],
        "include": list(ctx["scope"]["include"]),
        "exclude": list(ctx["scope"]["exclude"]),
    }
    scope_tier_a = ctx["scope"].get("tier_a_include")
    if scope_tier_a is not None:
        scope_obj["tier_a_include"] = list(scope_tier_a)
    scope_obj["notes"] = ctx["scope"]["notes"]

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
        "scope": scope_obj,
    }

    # Conditional: scope.rationale — canonical position is after `notes` and
    # before `amendments` (amendments is appended post-authoring by other
    # workflows and is never emitted here, so appending after notes yields the
    # canonical order). Absent → key omitted, matching the legacy-brief default.
    scope_rationale = ctx["scope"].get("rationale")
    if scope_rationale is not None:
        brief["scope"]["rationale"] = {
            "recommended": scope_rationale["recommended"],
            "chosen": scope_rationale["chosen"],
            "accepted_recommendation": scope_rationale["accepted_recommendation"],
            "heuristic": scope_rationale["heuristic"],
            "reason": scope_rationale["reason"],
            "recorded": scope_rationale["recorded"],
        }

    # Conditional: scope.amendments — additive audit log, emitted verbatim after
    # rationale (matches the schema doc order). The writer preserves it as-is;
    # the writing authority for entry shape is skf-create-skill / skf-update-skill.
    scope_amendments = ctx["scope"].get("amendments")
    if scope_amendments is not None:
        brief["scope"]["amendments"] = scope_amendments

    # Conditional: the component-library fields, verbatim, after amendments
    # and in the schema doc's order. Absent -> keys omitted.
    for field in ("registry_path", "ui_variants", "demo_patterns"):
        value = ctx["scope"].get(field)
        if value is not None:
            brief["scope"][field] = value

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

    # Conditional: target_ref / source_ref git refs — preserved verbatim when
    # present (monorepo tag escape hatch + auto-resolved ref). Emitted after
    # target_version so a ratify/re-write does not strip them.
    for ref_field in ("target_ref", "source_ref"):
        ref_val = ctx.get(ref_field)
        if ref_val is not None:
            brief[ref_field] = ref_val

    # Conditional: doc_urls (always emitted when present)
    #
    # Each entry carries the {url, label} contract plus an OPTIONAL `source`
    # provenance field (issue #432: language-registry | readme-detection |
    # homepage | pages-api | docs-folder). `source` is emitted ONLY when present
    # on the input entry — mirroring the source_authority null-drop discipline
    # below (lines ~448-454): a legacy/hand-authored entry without `source`
    # round-trips to exactly {url, label}, so a ratify/re-write of an old brief
    # stays byte-identical. (An explicit empty-string source is treated as
    # absent here; the schema enum is the real gate and rejects "" upstream.)
    doc_urls = ctx.get("doc_urls")
    if doc_urls:
        rendered_doc_urls: list[dict[str, Any]] = []
        for e in doc_urls:
            entry = {"url": e["url"], "label": e.get("label", "")}
            if e.get("source"):
                entry["source"] = e["source"]
            rendered_doc_urls.append(entry)
        brief["doc_urls"] = rendered_doc_urls

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
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise corrupt verbatim writes on Windows.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
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
_FLAT_SCOPE_KEYS = (
    "scope_type",
    "scope_include",
    "scope_exclude",
    "scope_notes",
    "scope_rationale",
    "scope_tier_a_include",
    "scope_amendments",
    "scope_registry_path",
    "scope_ui_variants",
    "scope_demo_patterns",
)


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
        # Optional authoring-time rationale. Null/absent → key dropped (same
        # null-drop semantics as doc_urls); when present it carries the full
        # six-subkey object validated by validate_context.
        if "scope_rationale" in flat and flat["scope_rationale"] is not None:
            scope["rationale"] = flat["scope_rationale"]
        # Optional stratified-scope tier-A include list and post-authoring
        # amendments log. Same null-drop semantics — preserved on a ratify
        # re-write so the brief's authored surface and audit trail survive.
        if "scope_tier_a_include" in flat and flat["scope_tier_a_include"] is not None:
            scope["tier_a_include"] = flat["scope_tier_a_include"]
        if "scope_amendments" in flat and flat["scope_amendments"] is not None:
            scope["amendments"] = flat["scope_amendments"]
        # Optional component-library fields: the same null-drop semantics.
        for field in ("registry_path", "ui_variants", "demo_patterns"):
            if flat.get(f"scope_{field}") is not None:
                scope[field] = flat[f"scope_{field}"]
        nested["scope"] = scope
    return nested


def _plain(value: Any) -> Any:
    """A YAML-loaded value with each unquoted date turned into its ISO text."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _overlay(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """`patch` laid over `base`: an object merges key by key, null removes the key, any other value replaces."""
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _overlay(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json_object(path: Path, flag: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as e:
        _die(f"write: cannot read the {flag} file {path}: {e}", code=2)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        _die(f"write: the {flag} file {path} is not JSON: {e}")
    if not isinstance(data, dict):
        _die(f"write: the {flag} file {path} must hold a JSON object")
    return data


def base_context(base_brief: Path, doc_urls_file: Path | None, patch_file: Path | None) -> dict[str, Any]:
    """The write context of the base brief form (see the module docstring)."""
    try:
        original = base_brief.read_bytes()
    except OSError as e:
        _die(f"write: cannot read the base brief {base_brief}: {e}", code=2)
    try:
        brief = yaml.safe_load(original.decode("utf-8-sig"))
    except (UnicodeDecodeError, yaml.YAMLError) as e:
        _die(f"write: the base brief {base_brief} is not YAML: {e}")
    if not isinstance(brief, dict):
        _die(f"write: the base brief {base_brief} holds no brief mapping")
    ctx = _plain(brief)
    if doc_urls_file is not None:
        merged = _read_json_object(doc_urls_file, "--doc-urls-file")
        if "doc_urls" not in merged:
            _die(f"write: the --doc-urls-file file {doc_urls_file} holds no doc_urls", field="doc_urls")
        ctx["doc_urls"] = merged["doc_urls"]
    if patch_file is not None:
        ctx = _overlay(ctx, _read_json_object(patch_file, "--patch-file"))
    if ctx.get("version_resolved") is None:
        ctx["version_resolved"] = ctx.get("version")
    return ctx


def cmd_write(target: Path, from_flat: bool = False, base_brief: Path | None = None,
              doc_urls_file: Path | None = None, patch_file: Path | None = None) -> int:
    if base_brief is not None:
        if from_flat:
            _die("write: --from-flat and --base-brief exclude each other")
        ctx = base_context(base_brief, doc_urls_file, patch_file)
    elif doc_urls_file is not None or patch_file is not None:
        _die("write: --doc-urls-file and --patch-file change a --base-brief")
    else:
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


AMEND_FIELDS = ("registry_path", "demo_patterns", "amendments")


def _check_amendments(entries: Any) -> list[dict[str, Any]]:
    """The amendment entries of an amend payload, checked (see the docstring)."""
    if not isinstance(entries, list):
        _die("amend: amendments must be an array of amendment objects", field="scope.amendments")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _die(f"amend: amendments[{i}] must be an object", field="scope.amendments")
        for key in ("path", "action", "reason", "workflow"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                _die(f"amend: amendments[{i}].{key} must be a non-empty string", field="scope.amendments")
        if not isinstance(entry.get("date"), str) or not ISO_DATE_RE.match(entry["date"]):
            _die(f"amend: amendments[{i}].date must be an ISO date (YYYY-MM-DD)", field="scope.amendments")
        category = entry.get("category")
        if category is not None and (not isinstance(category, str) or not category):
            _die(f"amend: amendments[{i}].category must be a non-empty string when present",
                 field="scope.amendments")
    return entries


def cmd_amend(target: Path) -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError as e:
        _die(f"amend: invalid JSON on stdin: {e}")
    if not isinstance(payload, dict):
        _die("amend: stdin must be a JSON object holding registry_path, demo_patterns or amendments")
    unknown = sorted(set(payload) - set(AMEND_FIELDS))
    if unknown:
        _die(f"amend: unknown field(s) {unknown}; expected some of {list(AMEND_FIELDS)}")
    given = [field for field in AMEND_FIELDS if payload.get(field) not in (None, [])]
    if not given:
        _die("amend: nothing to amend")
    entries = _check_amendments(payload["amendments"]) if "amendments" in given else []

    try:
        original = target.read_bytes()
    except OSError as e:
        _die(f"amend: cannot read {target}: {e}", code=2)
    try:
        brief = yaml.safe_load(original.decode("utf-8-sig"))
    except (UnicodeDecodeError, yaml.YAMLError) as e:
        _die(f"amend: {target} is not a YAML brief: {e}")
    if not isinstance(brief, dict) or not isinstance(brief.get("scope"), dict):
        _die(f"amend: {target} holds no scope mapping", field="scope")
    scope = brief["scope"]
    if entries:
        existing = scope.get("amendments")
        if existing is not None and not isinstance(existing, list):
            _die("amend: the brief's scope.amendments is not an array", field="scope.amendments")
        scope["amendments"] = [*(existing or []), *entries]
    for field in ("registry_path", "demo_patterns"):
        if field in given:
            scope[field] = payload[field]
    _check_component_fields(scope)

    backup = target.with_name(target.name + ".bak")
    try:
        backup.write_bytes(original)
    except OSError as e:
        _die(f"amend: cannot write {backup}: {e}", code=2)
    bytes_written = atomic_write(target, render_yaml(brief))
    print(json.dumps({
        "status": "ok",
        "brief_path": str(target.resolve()),
        "backup": str(backup.resolve()),
        "set": [field for field in given if field != "amendments"],
        "appended": len(entries),
        "bytes": bytes_written,
    }))
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
    p_write.add_argument("--base-brief", type=Path, metavar="FILE",
                         help="start from the brief in FILE (a skill-brief.yaml) instead of reading stdin")
    p_write.add_argument("--doc-urls-file", type=Path, metavar="FILE",
                         help="with --base-brief: replace doc_urls with the doc_urls of FILE "
                              "(skf-merge-doc-urls.py output)")
    p_write.add_argument("--patch-file", type=Path, metavar="FILE",
                         help="with --base-brief: lay the JSON object in FILE over the brief "
                              "(objects merge, null removes, other values replace)")

    p_amend = sub.add_parser(
        "amend",
        help=(
            "Apply answers (JSON on stdin) to an existing brief: set scope.registry_path and "
            "scope.demo_patterns, append scope.amendments entries, keep a .bak copy, atomic write"
        ),
    )
    p_amend.add_argument("--target", type=Path, required=True, help="Path to the skill-brief.yaml to amend")

    args = parser.parse_args()
    if args.cmd == "write":
        return cmd_write(args.target, from_flat=args.from_flat, base_brief=args.base_brief,
                         doc_urls_file=args.doc_urls_file, patch_file=args.patch_file)
    if args.cmd == "amend":
        return cmd_amend(args.target)
    return 2


def _force_utf8(*streams) -> None:
    """Reconfigure stdin, stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which would garble a payload's
    non-ASCII text (a description, an amendment's reason) read from stdin
    (reconfigured here, before the first read).
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
