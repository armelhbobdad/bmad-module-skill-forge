# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Render Quick Metadata — render metadata.json per the canonical
skill-template.md schema with quick-skill-specific population rules.

Pure renderer — no I/O beyond stdin/stdout. Reads a JSON payload of
extracted state on stdin and emits the corresponding metadata.json
on stdout. Replaces the hand-assembly the LLM previously did in
skf-quick-skill step 4 §4.

Constants vs. input-derived split mirrors step 4's documentation:

  Constants (always literal):
    skill_type            "single"
    spec_version          "1.3"
    source_authority      "community"
    confidence_tier       "Quick"
    generated_by          "quick-skill"
    confidence_distribution.t1, t2, t3                             0
    tool_versions.ast_grep, tool_versions.qmd                      null
    stats.exports_internal, stats.scripts_count, stats.assets_count 0
    stats.public_api_coverage, stats.total_coverage                 1.0

  Input-derived (from stdin payload):
    name, version, description, language, source_repo,
    source_root, source_commit, source_package,
    exports[], dependencies[], compatibility,
    provenance.language_hint, provenance.scope_hint,
    tool_versions.skf

  Computed:
    generation_date                 ISO 8601 UTC ("YYYY-MM-DDTHH:MM:SSZ")
    confidence_distribution.t1_low  count(exports)
    stats.exports_documented / public_api / total  count(exports)

Input JSON shape (stdin):

  {
    "name":           "foo",
    "version":        "1.2.3",                      (default "1.0.0")
    "description":    "...",                         (default "")
    "language":       "python",
    "source_repo":    "https://github.com/x/y",
    "source_root":    "src/foo",                     (optional)
    "source_commit":  "abc123",                      (optional)
    "source_package": "foo",                         (optional)
    "exports":        [{"name":"fn","type":"def"}]   or list of strings
    "dependencies":   ["a", "b"],                    (default [])
    "compatibility":  ">=3.10",                      (optional, default "")
    "language_hint":  null,                          (echoed verbatim)
    "scope_hint":     null,                          (echoed verbatim)
    "skf_version":    "1.2.0"                        (default "unknown")
  }

CLI:

  python3 skf-render-quick-metadata.py < input.json

Exit codes:

  0   success
  1   payload-level error (missing required field)
  2   stdin / argparse / JSON-decode error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys


REQUIRED_FIELDS = ("name", "language", "source_repo")


def _normalize_exports(raw) -> list[str]:
    """Accept either a list of strings or a list of {name, type, ...} dicts.
    Returns a flat list of export names in declaration order, deduplicated.
    """
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        name: str | None = None
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            v = item.get("name")
            if isinstance(v, str):
                name = v
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _iso_utc_now() -> str:
    """Returns 'YYYY-MM-DDTHH:MM:SSZ' for the current UTC instant."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_metadata(payload: dict, *, now_fn=_iso_utc_now) -> dict:
    """Render the metadata.json envelope. Pass `now_fn` to inject a
    deterministic timestamp in tests.
    """
    missing = [f for f in REQUIRED_FIELDS if not payload.get(f)]
    if missing:
        return {"_error": f"missing required field(s): {', '.join(missing)}"}

    exports = _normalize_exports(payload.get("exports"))
    export_count = len(exports)

    metadata = {
        "name": payload["name"],
        "version": payload.get("version") or "1.0.0",
        "description": payload.get("description") or "",
        "skill_type": "single",
        "source_authority": "community",
        "source_repo": payload["source_repo"],
        "source_root": payload.get("source_root") or "",
        "source_commit": payload.get("source_commit") or "",
        "source_package": payload.get("source_package") or payload["name"],
        "language": payload["language"],
        "generated_by": "quick-skill",
        "generation_date": now_fn(),
        "confidence_tier": "Quick",
        "spec_version": "1.3",
        "exports": exports,
        "confidence_distribution": {
            "t1": 0,
            "t1_low": export_count,
            "t2": 0,
            "t3": 0,
        },
        "tool_versions": {
            "ast_grep": None,
            "qmd": None,
            "skf": payload.get("skf_version") or "unknown",
        },
        "stats": {
            "exports_documented": export_count,
            "exports_public_api": export_count,
            "exports_internal": 0,
            "exports_total": export_count,
            "public_api_coverage": 1.0,
            "total_coverage": 1.0,
            "scripts_count": 0,
            "assets_count": 0,
        },
        "dependencies": payload.get("dependencies") or [],
        "compatibility": payload.get("compatibility") or "",
        "provenance": {
            "language_hint": payload.get("language_hint"),
            "scope_hint": payload.get("scope_hint"),
        },
    }
    return metadata


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Render skf-quick-skill metadata.json from extracted state on stdin.",
    )
    parser.parse_args(argv)  # currently no flags; kept for forward compat

    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("error: no input on stdin (expected JSON payload)\n")
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"error: stdin JSON parse error: {e}\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("error: stdin payload must be a JSON object\n")
        return 2

    result = render_metadata(payload)
    if "_error" in result:
        sys.stderr.write(f"error: {result['_error']}\n")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
