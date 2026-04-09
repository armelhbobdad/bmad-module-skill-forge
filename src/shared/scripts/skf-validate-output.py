# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Validate Output — Validate skill package artifacts.

Validates SKILL.md frontmatter, context-snippet.md format, and metadata.json
schema against agentskills.io specification. Outputs JSON validation results.

CLI: python3 skf-validate-output.py <skill-package-dir>
     python3 skf-validate-output.py <skill-package-dir> --generated-by quick-skill
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def validate_frontmatter(content, skill_name=None):
    """Validate SKILL.md frontmatter. Returns list of issues."""
    issues = []

    # Check frontmatter delimiters
    if not content.startswith("---\n"):
        issues.append({"severity": "high", "field": "frontmatter", "message": "Missing opening --- delimiter"})
        return issues

    # Find closing --- on its own line (not a substring match inside YAML values)
    end_idx = -1
    for i, line in enumerate(content.split("\n")[1:], start=1):
        if line.rstrip() == "---":
            end_idx = sum(len(l) + 1 for l in content.split("\n")[:i])
            break
    if end_idx == -1:
        issues.append({"severity": "high", "field": "frontmatter", "message": "Missing closing --- delimiter"})
        return issues

    fm_text = content[4:end_idx].strip()
    fm = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip("'\"")

    # Required fields
    name = fm.get("name", "")
    if not name:
        issues.append({"severity": "high", "field": "name", "message": "name field missing or empty"})
    elif not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", name) or len(name) > 64:
        issues.append({"severity": "high", "field": "name", "message": f"name must be lowercase alphanumeric + hyphens, 1-64 chars, got: {name}"})

    if skill_name and name and name != skill_name:
        issues.append({"severity": "high", "field": "name", "message": f"name '{name}' does not match directory name '{skill_name}'"})

    desc = fm.get("description", "")
    if not desc:
        issues.append({"severity": "high", "field": "description", "message": "description field missing or empty"})

    # Allowed fields
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    for key in fm:
        if key not in allowed:
            issues.append({"severity": "low", "field": key, "message": f"Unknown frontmatter field: {key}"})

    return issues


def validate_body_structure(content):
    """Validate SKILL.md body has required sections. Returns list of issues."""
    issues = []
    body = content.split("---", 2)[-1] if content.startswith("---") else content

    required_sections = ["Overview", "Key Exports", "Usage"]
    for section in required_sections:
        pattern = rf"^##\s+.*{re.escape(section)}"
        if not re.search(pattern, body, re.MULTILINE | re.IGNORECASE):
            issues.append({"severity": "medium", "field": f"section:{section}", "message": f"Missing ## {section} section"})

    return issues


def validate_context_snippet(content):
    """Validate context-snippet.md format. Returns list of issues."""
    issues = []

    if not content or not content.strip():
        issues.append({"severity": "high", "field": "content", "message": "Context snippet is empty"})
        return issues

    lines = content.strip().split("\n")

    # First line: [name vVersion]|root: prefix
    if lines:
        first = lines[0]
        if not re.match(r"\[.+ v.+\]\|root:", first):
            issues.append({"severity": "medium", "field": "line1", "message": f"First line doesn't match expected pattern: [{first[:50]}...]"})

    # Second line: |IMPORTANT:
    if len(lines) > 1:
        if not lines[1].startswith("|IMPORTANT:"):
            issues.append({"severity": "medium", "field": "line2", "message": "Second line should start with |IMPORTANT:"})

    # Approximate token count (rough: ~4 chars per token)
    approx_tokens = len(content) // 4
    if approx_tokens < 40:
        issues.append({"severity": "low", "field": "length", "message": f"Context snippet may be too short (~{approx_tokens} tokens)"})
    elif approx_tokens > 200:
        issues.append({"severity": "low", "field": "length", "message": f"Context snippet may be too long (~{approx_tokens} tokens)"})

    return issues


def validate_metadata_json(data, generated_by=None):
    """Validate metadata.json fields. Returns list of issues."""
    issues = []

    required_str = ["name", "version", "source_authority", "language", "generation_date"]
    for field in required_str:
        val = data.get(field)
        if not val or not isinstance(val, str):
            issues.append({"severity": "high", "field": field, "message": f"{field} missing or not a string"})

    # source_repo should be a URL
    repo = data.get("source_repo", "")
    if not repo:
        issues.append({"severity": "medium", "field": "source_repo", "message": "source_repo missing"})

    # generated_by check
    gb = data.get("generated_by", "")
    if not gb:
        issues.append({"severity": "medium", "field": "generated_by", "message": "generated_by missing"})
    elif generated_by and gb != generated_by:
        issues.append({"severity": "low", "field": "generated_by", "message": f"generated_by is '{gb}', expected '{generated_by}'"})

    # confidence_tier
    if not data.get("confidence_tier"):
        issues.append({"severity": "medium", "field": "confidence_tier", "message": "confidence_tier missing"})

    # stats
    stats = data.get("stats", {})
    if not isinstance(stats, dict):
        issues.append({"severity": "high", "field": "stats", "message": "stats must be an object"})
    else:
        required_stats = ["exports_documented", "exports_public_api", "exports_total", "public_api_coverage", "total_coverage"]
        for field in required_stats:
            val = stats.get(field)
            if val is None:
                issues.append({"severity": "medium", "field": f"stats.{field}", "message": f"stats.{field} missing"})
            elif not isinstance(val, (int, float)):
                issues.append({"severity": "medium", "field": f"stats.{field}", "message": f"stats.{field} must be a number"})

    return issues


def validate_skill_package(skill_dir, generated_by=None):
    """Validate a complete skill package directory."""
    skill_dir = Path(skill_dir)
    skill_name = skill_dir.name

    result = {
        "status": "ok",
        "skill_dir": str(skill_dir),
        "skill_name": skill_name,
        "files_found": {},
        "validation": {},
        "summary": {"total_issues": 0, "by_severity": {"high": 0, "medium": 0, "low": 0}},
    }

    # Check file existence
    files = {
        "SKILL.md": skill_dir / "SKILL.md",
        "context-snippet.md": skill_dir / "context-snippet.md",
        "metadata.json": skill_dir / "metadata.json",
    }

    for name, path in files.items():
        result["files_found"][name] = path.exists()

    # Validate SKILL.md
    skill_md_path = files["SKILL.md"]
    if skill_md_path.exists():
        content = skill_md_path.read_text()
        fm_issues = validate_frontmatter(content, skill_name)
        body_issues = validate_body_structure(content)
        result["validation"]["skill_md"] = {"frontmatter": fm_issues, "body": body_issues}
        for issue in fm_issues + body_issues:
            result["summary"]["total_issues"] += 1
            result["summary"]["by_severity"][issue["severity"]] += 1
    else:
        result["validation"]["skill_md"] = {"error": "SKILL.md not found"}
        result["summary"]["total_issues"] += 1
        result["summary"]["by_severity"]["high"] += 1

    # Validate context-snippet.md
    snippet_path = files["context-snippet.md"]
    if snippet_path.exists():
        content = snippet_path.read_text()
        snippet_issues = validate_context_snippet(content)
        result["validation"]["context_snippet"] = {"issues": snippet_issues}
        for issue in snippet_issues:
            result["summary"]["total_issues"] += 1
            result["summary"]["by_severity"][issue["severity"]] += 1
    else:
        result["validation"]["context_snippet"] = {"skipped": "context-snippet.md not found"}

    # Validate metadata.json
    meta_path = files["metadata.json"]
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            meta_issues = validate_metadata_json(meta, generated_by)
            result["validation"]["metadata"] = {"issues": meta_issues}
            for issue in meta_issues:
                result["summary"]["total_issues"] += 1
                result["summary"]["by_severity"][issue["severity"]] += 1
        except json.JSONDecodeError as e:
            result["validation"]["metadata"] = {"error": f"JSON parse error: {e}"}
            result["summary"]["total_issues"] += 1
            result["summary"]["by_severity"]["high"] += 1
    else:
        result["validation"]["metadata"] = {"skipped": "metadata.json not found"}

    # Overall pass/fail
    result["result"] = "PASS" if result["summary"]["by_severity"]["high"] == 0 else "FAIL"

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 skf-validate-output.py <skill-package-dir> [--generated-by <generator>]", file=sys.stderr)
        sys.exit(1)

    pkg_dir = sys.argv[1]
    gen_by = None
    if "--generated-by" in sys.argv:
        idx = sys.argv.index("--generated-by")
        if idx + 1 < len(sys.argv):
            gen_by = sys.argv[idx + 1]

    result = validate_skill_package(pkg_dir, generated_by=gen_by)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["result"] == "PASS" else 1)
