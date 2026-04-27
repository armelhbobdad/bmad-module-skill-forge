# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Merge CCC Exclusions — Set-union merge of SKF exclusion patterns.

Replaces the prose-driven validation + merge logic in `src/skf-setup/
steps-c/step-01b-ccc-index.md` §2b with one Python invocation. Reads
`.cocoindex_code/settings.yml`, applies PR #248's config-value
validation rules to reject inputs that would silently produce a
malformed glob (the empty-value-becomes-`**/`-matches-everything bug
that would silently exclude the entire repo from indexing), and
performs an idempotent set-union merge of the SKF exclusion list into
the existing `exclude_patterns` array.

Always-included patterns (4 hardcoded — no config needed):

  **/_bmad           SKF framework module (workflows, agents, knowledge)
  **/_bmad-output    Build output artifacts
  **/.claude         Claude Code configuration
  **/_skf-learn      SKF learning materials

Conditionally-included patterns (2 from config — validated before use):

  **/{skills_output_folder}   Generated skill files
  **/{forge_data_folder}      Compilation workspace

Validation rules for the 2 conditional values (PR #248):

  - REJECT empty or whitespace-only values
    → would produce `**/`, matching every path → ccc indexes nothing
  - REJECT values starting with `/`, `~/`, or `./`
    → produces `**//abs/path`, `**/~/x`, or `**/./rel` — malformed glob
  - REJECT values containing glob meta-characters (`*`, `?`, `[`)
    → interpolation collides with the surrounding pattern syntax

Rejected values are SKIPPED (the pattern is not added) and a warning
is appended to the output. The 4 always-include patterns are applied
unconditionally — config-value rejection cannot disable indexing
entirely.

CLI:

  python3 skf-merge-ccc-exclusions.py \\
      --project-root /abs/path \\
      --skills-output-folder skills \\
      --forge-data-folder _bmad-output/forge-data

Output (single JSON document on stdout):

  {
    "status": "ok",
    "version": "v1",
    "settings_yml_existed":   bool,
    "settings_yml_path":      "/abs/path/.cocoindex_code/settings.yml",
    "patterns_added":         int,
    "patterns_added_list":    ["**/_bmad", ...],
    "patterns_already_present": int,
    "written":                bool,
    "warnings":               ["string", ...]
  }

`written` is false when no new patterns needed adding (idempotent
re-run — no I/O wasted). Non-zero `warnings` does NOT prevent the
write — always-include patterns still merge.

Atomic writes via temp + fsync + rename (mirrors skf-atomic-write.py).
Concurrent writers must coordinate via external `flock` (the typical
pattern for shared-file mutation in this module).

Exit codes:
  0 success (warnings, if any, are still on the success path)
  1 user error (bad args, missing required flag, malformed settings.yml)
  2 internal error (write failure)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml


ALWAYS_INCLUDE = (
    "**/_bmad",
    "**/_bmad-output",
    "**/.claude",
    "**/_skf-learn",
)
GLOB_META_CHARS = set("*?[")


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    payload.setdefault("version", "v1")
    print(json.dumps(payload))


def _atomic_write(target: Path, content: str) -> None:
    """Crash-safe write via temp + fsync + rename. Mirrors skf-atomic-write.py."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".skf-tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, content.encode("utf-8"))
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
        _die(2, f"atomic write failed for {target}: {e}")


# ─── Config-value validation (PR #248 rules) ────────────────────────────────


def validate_config_value(key: str, raw_value: str) -> tuple[str | None, str | None]:
    """Validate a config value used to interpolate `**/{value}`.

    Returns (cleaned_value, warning_or_None). When cleaned_value is None
    the value was rejected and the caller MUST NOT add the pattern.
    """
    if raw_value is None or not str(raw_value).strip():
        return None, (
            f"{key} is empty or whitespace-only; refused for ccc exclusion because "
            f"interpolating it would produce `**/`, which matches every path and "
            f"would silently exclude the entire repository from indexing — fix the "
            f"value in {{project-root}}/_bmad/skf/config.yaml"
        )

    value = str(raw_value).strip()

    if value.startswith("/") or value.startswith("~/") or value.startswith("./"):
        return None, (
            f"{key} is an absolute or anchored path; refused for ccc exclusion "
            f"because interpolating it would produce a malformed glob — fix the "
            f"value in {{project-root}}/_bmad/skf/config.yaml to a repo-relative path"
        )

    if any(ch in GLOB_META_CHARS for ch in value):
        return None, (
            f"{key} contains glob meta-character (*, ?, [); refused for ccc "
            f"exclusion because interpolation collides with the surrounding "
            f"pattern syntax — fix the value in {{project-root}}/_bmad/skf/config.yaml"
        )

    return value, None


# ─── Pattern assembly ───────────────────────────────────────────────────────


def assemble_patterns(skills_output_folder: str, forge_data_folder: str
                      ) -> tuple[list[str], list[str]]:
    """Return (validated_patterns_to_add, warnings).

    Validated patterns include the 4 unconditional ones plus any of the
    2 config-driven ones whose value passed validation.
    """
    patterns = list(ALWAYS_INCLUDE)
    warnings: list[str] = []

    cleaned, warn = validate_config_value("skills_output_folder", skills_output_folder)
    if cleaned is not None:
        patterns.append(f"**/{cleaned}")
    elif warn:
        warnings.append(warn)

    cleaned, warn = validate_config_value("forge_data_folder", forge_data_folder)
    if cleaned is not None:
        patterns.append(f"**/{cleaned}")
    elif warn:
        warnings.append(warn)

    return patterns, warnings


# ─── settings.yml read / merge / render ─────────────────────────────────────


def read_settings_yml(path: Path) -> tuple[dict, bool]:
    """Return (parsed_dict, existed_before).

    Missing file → ({}, False). Existing file is parsed; non-mapping top-level
    or YAML errors exit with a clear message.
    """
    if not path.exists():
        return {}, False
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        _die(1, f"failed to parse {path}: {e}")
    if data is None:
        return {}, True
    if not isinstance(data, dict):
        _die(1, f"expected mapping at top of {path}, got {type(data).__name__}")
    return data, True


def merge_patterns(existing_patterns: list[str], to_add: list[str]
                   ) -> tuple[list[str], list[str]]:
    """Append `to_add` entries to `existing_patterns` if not already present.

    Returns (merged_patterns, newly_added_patterns). Order of existing
    entries is preserved; new entries are appended in the order given.
    """
    seen = set(existing_patterns)
    merged = list(existing_patterns)
    newly_added: list[str] = []
    for p in to_add:
        if p in seen:
            continue
        seen.add(p)
        merged.append(p)
        newly_added.append(p)
    return merged, newly_added


def render_settings_yml(data: dict, original_text: str | None) -> str:
    """Render the updated settings dict as YAML.

    For first-time-write (no original text), emit a minimal file with
    just the exclude_patterns the script controls. For updates, dump the
    full data structure with PyYAML — this DROPS comments from the
    original file. The cocoindex CLI is the only consumer of settings.yml
    contents, and it doesn't care about comments. User-customized
    exclude_patterns entries are preserved (set-union, not overwrite);
    other top-level keys (if any) are also preserved.
    """
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def cmd_merge(project_root: Path, skills_output_folder: str, forge_data_folder: str) -> None:
    target = project_root / ".cocoindex_code" / "settings.yml"

    patterns_to_add, warnings = assemble_patterns(skills_output_folder, forge_data_folder)
    data, existed = read_settings_yml(target)

    existing_excludes = data.get("exclude_patterns", []) or []
    if not isinstance(existing_excludes, list):
        _die(1, f"exclude_patterns in {target} is not a list "
                f"(got {type(existing_excludes).__name__})")
    # Normalize entries to strings (cocoindex tolerates non-string entries
    # but we want byte-identical comparison)
    existing_excludes = [str(p) for p in existing_excludes]

    merged, newly_added = merge_patterns(existing_excludes, patterns_to_add)
    patterns_already_present = len(patterns_to_add) - len(newly_added)

    if not newly_added:
        # Idempotent re-run — no write, no mtime change.
        _ok({
            "settings_yml_existed":     existed,
            "settings_yml_path":        str(target),
            "patterns_added":           0,
            "patterns_added_list":      [],
            "patterns_already_present": patterns_already_present,
            "written":                  False,
            "warnings":                 warnings,
        })
        return

    data["exclude_patterns"] = merged
    rendered = render_settings_yml(data, None)
    _atomic_write(target, rendered)

    _ok({
        "settings_yml_existed":     existed,
        "settings_yml_path":        str(target),
        "patterns_added":           len(newly_added),
        "patterns_added_list":      newly_added,
        "patterns_already_present": patterns_already_present,
        "written":                  True,
        "warnings":                 warnings,
    })


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge SKF exclusion patterns into .cocoindex_code/settings.yml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project-root", type=Path, required=True,
        help="Absolute path to the project root. Script writes/reads "
             "{project-root}/.cocoindex_code/settings.yml.",
    )
    parser.add_argument(
        "--skills-output-folder", default="",
        help="Raw value of skills_output_folder from {project-root}/_bmad/skf/config.yaml. "
             "Validated before being interpolated into `**/{value}`. Empty/absolute/glob-meta "
             "values are rejected with a warning.",
    )
    parser.add_argument(
        "--forge-data-folder", default="",
        help="Raw value of forge_data_folder from {project-root}/_bmad/skf/config.yaml. "
             "Same validation as --skills-output-folder.",
    )
    args = parser.parse_args()

    cmd_merge(args.project_root, args.skills_output_folder, args.forge_data_folder)


if __name__ == "__main__":
    main()
