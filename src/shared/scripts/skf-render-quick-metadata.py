# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Render Quick Metadata: render metadata.json per the canonical
skill-template.md schema with quick-skill-specific population rules.

Replaces the hand-assembly the LLM previously did in skf-quick-skill step 4
section 4. The export list, the dependencies and the package's version come
from the files step 3 wrote (skf-extract-public-api.py's output, or
skf-skills-module.py extract's), and the SKF version from the installed
module, so the model stages only the fields it decides: no export list and
no file probe passes through a shell string.

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

  Input-derived:
    name, version, description, language, source_repo,
    source_root, source_commit, source_package,
    exports[], dependencies[], compatibility,
    provenance.language_hint, provenance.scope_hint,
    tool_versions.skf

  Computed:
    generation_date                 ISO 8601 UTC ("YYYY-MM-DDTHH:MM:SSZ")
    confidence_distribution.t1_low  count(exports)
    stats.exports_documented / public_api / total  count(exports)

CLI:

  uv run skf-render-quick-metadata.py --input <metadata-input.json> \\
      [--extraction <file>]... [--skf-root <dir>] [--output <metadata.json>]
  python3 skf-render-quick-metadata.py < payload.json

With --input, the payload is that file (a quoted heredoc stages it, so a
description holding an apostrophe, a quote or a `$` arrives as written),
and each --extraction file is the JSON step 3 printed for one module, in
module order (the parent first). A payload field that is absent or null
takes its value from them:

  exports        every extraction's exports[] names, in order, each once
                 (a payload `exports` list is the --exports override and
                 wins)
  dependencies   every extraction's dependencies[], each once
  version        the first extraction's version that is set, else "1.0.0"
                 (a payload version, the target's pinned version, wins)
  source_package the first extraction's package_name, else name
  description    the first extraction's description

and tool_versions.skf, unless the payload names skf_version, is probed
under --skf-root (the installed module, {project-root}/_bmad/skf): the
`version` of its package.json, else the first line of its VERSION file,
else "unknown". --output also writes the rendered metadata.json there.

Without --input, the whole payload comes on stdin, every field typed:

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

The rendered metadata.json is printed on stdout either way.

Exit codes:

  0   success
  1   payload-level error (missing required field: name, language or
      source_repo)
  2   stdin / argparse / JSON-decode error, or an --input, --extraction or
      --output file that cannot be read or written
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


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


def probe_skf_version(skf_root: str | Path | None) -> str:
    """The installed SKF's version: package.json `version`, else the VERSION file's first line, else "unknown"."""
    if not skf_root:
        return "unknown"
    root = Path(skf_root)
    try:
        version = json.loads((root / "package.json").read_text(encoding="utf-8-sig")).get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except (OSError, ValueError, AttributeError):
        pass
    try:
        lines = (root / "VERSION").read_text(encoding="utf-8-sig").strip().splitlines()
        if lines and lines[0].strip():
            return lines[0].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return "unknown"


def merge_extractions(payload: dict, extractions: list[dict], skf_version: str | None = None) -> dict:
    """The full renderer payload: the staged fields, then what the extraction files give."""
    merged = dict(payload)

    def first(key: str):
        return next((e[key] for e in extractions if isinstance(e.get(key), str) and e[key].strip()), None)

    if not isinstance(merged.get("exports"), list):
        merged["exports"] = [x for e in extractions for x in (e.get("exports") or []) if isinstance(x, (dict, str))]
    if not isinstance(merged.get("dependencies"), list):
        deps = [d for e in extractions for d in (e.get("dependencies") or []) if isinstance(d, str)]
        merged["dependencies"] = list(dict.fromkeys(deps))
    for key, source in (("version", "version"), ("source_package", "package_name"), ("description", "description")):
        if not merged.get(key):
            merged[key] = first(source)
    if not merged.get("skf_version") and skf_version is not None:
        merged["skf_version"] = skf_version
    return merged


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


def _read_object(path: str, flag: str) -> dict:
    """A JSON object from a file; raises ValueError with the message to print."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"cannot read {flag} {path}: {getattr(e, 'strerror', None) or e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"{flag} {path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{flag} {path} must hold a JSON object")
    return data


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Render skf-quick-skill metadata.json from staged fields and the extraction files "
                    "(or from a whole payload on stdin).",
    )
    parser.add_argument("--input", help="the staged fields (metadata-input.json); without it, stdin")
    parser.add_argument("--extraction", action="append", default=[],
                        help="step 3's extraction output for one module (repeatable, parent first)")
    parser.add_argument("--skf-root", help="the installed SKF module folder to read its version from")
    parser.add_argument("--output", help="also write the rendered metadata.json here")
    args = parser.parse_args(argv)

    if args.input is None:
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
    else:
        try:
            payload = _read_object(args.input, "--input")
            extractions = [_read_object(path, "--extraction") for path in args.extraction]
        except ValueError as e:
            sys.stderr.write(f"error: {e}\n")
            return 2
        payload = merge_extractions(payload, extractions, probe_skf_version(args.skf_root))

    result = render_metadata(payload)
    if "_error" in result:
        sys.stderr.write(f"error: {result['_error']}\n")
        return 1
    text = json.dumps(result, indent=2)
    if args.output:
        try:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError as e:
            sys.stderr.write(f"error: cannot write --output {args.output}: {e.strerror or e}\n")
            return 2
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
