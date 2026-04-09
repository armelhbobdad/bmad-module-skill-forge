# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""SKF Validate Frontmatter — agentskills.io frontmatter compliance checker.

Validates SKILL.md frontmatter against the agentskills.io specification.
Aligned with the canonical reference implementation at
agentskills/agentskills/skills-ref/src/skills_ref/validator.py.

Designed for pre-check use in test-skill, create-skill, update-skill, and
export-skill workflows. Returns structured JSON for deterministic integration.

CLI:
  python3 skf-validate-frontmatter.py <skill-md-path>
  python3 skf-validate-frontmatter.py <skill-md-path> --skill-dir-name <name>

Input:
  Path to a SKILL.md file.
  Optional --skill-dir-name: expected directory name for name-match check.
  If omitted, derived from the parent directory of the SKILL.md path.

Output:
  JSON object:
    status:     "pass" | "fail" | "warn"
    issues:     list of { severity, field, message }
    frontmatter: parsed frontmatter dict (if parseable)
    summary:    { total, high, medium, low }

Exit codes:
  0  — pass (no high-severity issues)
  1  — fail (high-severity issues found) or error
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import yaml

# agentskills.io permitted frontmatter fields (matches canonical validator.py)
ALLOWED_FIELDS = frozenset({
    "name", "description", "license", "compatibility", "metadata", "allowed-tools",
})

MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500


def parse_frontmatter(content: str) -> tuple[dict | None, list[dict]]:
    """Extract and parse YAML frontmatter from SKILL.md content.

    Returns (parsed_dict, issues). If frontmatter is structurally broken,
    parsed_dict is None and issues contains the structural error.
    """
    issues: list[dict] = []

    if not content.startswith("---\n") and not content.startswith("---\r\n"):
        issues.append({
            "severity": "high",
            "field": "frontmatter",
            "message": "Missing opening --- delimiter",
        })
        return None, issues

    # Find closing --- on its own line (not a substring inside YAML values)
    closing_idx = -1
    search_start = content.index("\n") + 1  # skip past opening ---\n
    for i, line in enumerate(content[search_start:].split("\n")):
        if line.rstrip("\r") == "---":
            closing_idx = search_start + sum(len(l) + 1 for l in content[search_start:].split("\n")[:i])
            break
    if closing_idx == -1:
        issues.append({
            "severity": "high",
            "field": "frontmatter",
            "message": "Missing closing --- delimiter",
        })
        return None, issues

    # Extract text between opening and closing delimiters
    fm_text = content[search_start:closing_idx]

    # Parse with PyYAML for proper YAML handling (nested metadata, multi-line values)
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        issues.append({
            "severity": "high",
            "field": "frontmatter",
            "message": f"Invalid YAML in frontmatter: {exc}",
        })
        return None, issues

    if fm is None:
        # Empty frontmatter block
        fm = {}

    if not isinstance(fm, dict):
        issues.append({
            "severity": "high",
            "field": "frontmatter",
            "message": "Frontmatter must be a YAML mapping",
        })
        return None, issues

    # Normalize metadata sub-dict values to strings (matches canonical parser.py)
    if "metadata" in fm and isinstance(fm["metadata"], dict):
        fm["metadata"] = {str(k): str(v) for k, v in fm["metadata"].items()}

    return fm, issues


def _validate_name(name: str, skill_dir_name: str | None) -> list[dict]:
    """Validate skill name format. Aligned with canonical validator.py."""
    issues: list[dict] = []

    if not name or not isinstance(name, str) or not name.strip():
        issues.append({
            "severity": "high",
            "field": "name",
            "message": "name field missing or empty",
        })
        return issues

    name = unicodedata.normalize("NFKC", name.strip())

    if len(name) > MAX_SKILL_NAME_LENGTH:
        issues.append({
            "severity": "high",
            "field": "name",
            "message": f"name exceeds {MAX_SKILL_NAME_LENGTH} chars ({len(name)} chars)",
        })

    if name != name.lower():
        issues.append({
            "severity": "high",
            "field": "name",
            "message": f"name '{name}' must be lowercase",
        })

    if name.startswith("-") or name.endswith("-"):
        issues.append({
            "severity": "high",
            "field": "name",
            "message": "name cannot start or end with a hyphen",
        })

    if "--" in name:
        issues.append({
            "severity": "high",
            "field": "name",
            "message": "name cannot contain consecutive hyphens",
        })

    if not all(c.isalnum() or c == "-" for c in name):
        issues.append({
            "severity": "high",
            "field": "name",
            "message": f"name '{name}' contains invalid characters (only letters, digits, and hyphens allowed)",
        })

    # Directory name match (with Unicode normalization)
    if skill_dir_name:
        dir_name = unicodedata.normalize("NFKC", skill_dir_name)
        if dir_name != name:
            issues.append({
                "severity": "high",
                "field": "name",
                "message": f"name '{name}' does not match directory name '{skill_dir_name}'",
            })

    return issues


def validate_frontmatter(
    content: str,
    skill_dir_name: str | None = None,
) -> dict:
    """Validate SKILL.md frontmatter against agentskills.io spec.

    Returns a result dict with status, issues, frontmatter, and summary.
    """
    fm, issues = parse_frontmatter(content)

    if fm is not None:
        # Name validation
        name = fm.get("name", "")
        issues.extend(_validate_name(name, skill_dir_name))

        # Description: required, non-empty, max 1024 chars
        desc = fm.get("description", "")
        if not desc or not isinstance(desc, str) or not desc.strip():
            issues.append({
                "severity": "high",
                "field": "description",
                "message": "description field missing or empty",
            })
        elif len(desc) > MAX_DESCRIPTION_LENGTH:
            issues.append({
                "severity": "medium",
                "field": "description",
                "message": f"description exceeds {MAX_DESCRIPTION_LENGTH} chars ({len(desc)} chars)",
            })

        # Compatibility: optional, max 500 chars
        compat = fm.get("compatibility")
        if compat is not None:
            if not isinstance(compat, str):
                issues.append({
                    "severity": "medium",
                    "field": "compatibility",
                    "message": "compatibility must be a string",
                })
            elif len(compat) > MAX_COMPATIBILITY_LENGTH:
                issues.append({
                    "severity": "medium",
                    "field": "compatibility",
                    "message": f"compatibility exceeds {MAX_COMPATIBILITY_LENGTH} chars ({len(compat)} chars)",
                })

        # Unknown fields
        for key in fm:
            if key not in ALLOWED_FIELDS:
                issues.append({
                    "severity": "low",
                    "field": key,
                    "message": f"Unknown frontmatter field: '{key}'",
                })

    # Build summary
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        severity_counts[issue["severity"]] += 1

    if severity_counts["high"] > 0:
        status = "fail"
    elif severity_counts["medium"] > 0 or severity_counts["low"] > 0:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "issues": issues,
        "frontmatter": fm,
        "summary": {
            "total": len(issues),
            **severity_counts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skf-validate-frontmatter.py",
        description=(
            "Validate SKILL.md frontmatter against agentskills.io specification.\n"
            "\n"
            "Checks: frontmatter delimiters, name format (Unicode letters + digits +\n"
            "hyphens, no consecutive/trailing hyphens), name-directory match,\n"
            "description presence and length, compatibility length, and unknown fields.\n"
            "\n"
            "Exit code 0 means pass (no high-severity issues).\n"
            "Exit code 1 means fail (high-severity issues found)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "skill_md",
        metavar="SKILL.md",
        help="path to the SKILL.md file to validate",
    )
    parser.add_argument(
        "--skill-dir-name",
        metavar="NAME",
        default=None,
        help="expected skill directory name (default: derived from parent directory)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="write JSON output to FILE instead of stdout",
    )

    args = parser.parse_args()
    skill_md_path = Path(args.skill_md)

    if not skill_md_path.exists():
        result = {
            "status": "fail",
            "issues": [{"severity": "high", "field": "file", "message": f"File not found: {skill_md_path}"}],
            "frontmatter": None,
            "summary": {"total": 1, "high": 1, "medium": 0, "low": 0},
        }
    else:
        content = skill_md_path.read_text(encoding="utf-8")
        skill_dir_name = args.skill_dir_name or skill_md_path.parent.name
        result = validate_frontmatter(content, skill_dir_name)

    output_text = json.dumps(result, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output_text + "\n", encoding="utf-8")
    else:
        print(output_text)

    return 0 if result["status"] != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
