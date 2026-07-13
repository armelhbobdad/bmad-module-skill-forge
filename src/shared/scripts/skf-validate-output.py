# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Validate Output — Validate skill package artifacts.

Validates SKILL.md frontmatter, context-snippet.md format, and metadata.json
schema against agentskills.io specification. Outputs JSON validation results.

Two package shapes are supported via --skill-type (default: individual):
  individual — the single-skill schema: SKILL.md body sections
               (Overview/Description/Key Exports/Usage) and metadata.json
               fields (source_repo, stats.*). This is the legacy default and
               is unchanged for existing callers (quick-skill, create-skill).
  stack      — the capstone stack schema: skips the individual body/metadata
               checks and instead validates the stack count-equalities
               (library_count vs per-library reference files; integration_count
               vs integration pair files; confidence_distribution sum vs
               library_count), emitted under validation.stack_counts.

The --export-gate flag selects a third, self-contained mode used by
skf-export-skill's publishing gate (load-skill.md §2 + package.md §1-3). It is
additive and orthogonal to --skill-type: it does NOT touch the individual/stack
code path above, so existing callers keep byte-identical output. Under the flag
the script emits the deterministic verdict the export prompt previously derived
by hand each run:
  - metadata.json required-field presence for the full agentskills.io set
    (name, version, skill_type, source_authority, exports, generation_date,
    confidence_tier) as high-severity issues under validation.metadata.issues;
  - enum-membership checks (skill_type, source_authority, confidence_tier) as
    high-severity issues under validation.metadata.enum_issues;
  - SKILL.md Section 7b (Scripts & Assets) cross-reference against on-disk
    scripts/ and assets/ files, under validation.crossref_7b.{missing,orphans}
    (a §7b-named file absent on disk is high; an on-disk file not named in §7b
    is a low orphan warning);
  - a deterministic export_status ∈ READY / WARNINGS / NOT_READY alongside the
    existing PASS/FAIL result (NOT_READY on any high issue, WARNINGS when only
    medium/low issues remain, READY when clean).

CLI: python3 skf-validate-output.py <skill-package-dir>
     python3 skf-validate-output.py <skill-package-dir> --generated-by quick-skill
     python3 skf-validate-output.py <skill-package-dir> --skip-frontmatter
     python3 skf-validate-output.py <skill-package-dir> --skill-type stack
     python3 skf-validate-output.py <skill-package-dir> --export-gate
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

    required_sections = ["Overview", "Description", "Key Exports", "Usage"]
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


# --- Export-gate mode (skf-export-skill publishing gate) -------------------
#
# These helpers back the --export-gate flag only. They are additive: nothing
# above (individual / stack modes) calls them, so existing callers of
# validate_skill_package() keep byte-identical output.

_EXPORT_GATE_ENUMS = {
    "skill_type": ("single", "stack"),
    "source_authority": ("official", "internal", "community"),
    "confidence_tier": ("Quick", "Forge", "Forge+", "Deep"),
}

# Matches a scripts/… or assets/… path token (e.g. `scripts/run.py`). The
# leading filename char must be alphanumeric/dot/underscore so a bare
# `scripts/` (the §7b directory note with nothing after the slash) is not
# captured as a file reference.
_SECTION_7B_PATH_RE = re.compile(r"(?:scripts|assets)/[A-Za-z0-9._][A-Za-z0-9._/\-]*")


def validate_metadata_export_gate(data):
    """agentskills.io export-gate metadata validation.

    Returns (required_issues, enum_issues). Required-field presence for the full
    agentskills.io set is high-severity; enum-membership mismatches are
    high-severity. An empty `exports` array is a low warning (matching
    load-skill.md §2's "warn if empty — graceful handling"), not a hard halt.
    """
    required_issues = []
    enum_issues = []

    # String required fields — high-severity presence checks.
    for field in ("name", "version", "skill_type", "source_authority",
                  "generation_date", "confidence_tier"):
        val = data.get(field)
        if not val or not isinstance(val, str):
            required_issues.append({
                "severity": "high",
                "field": field,
                "message": f"{field} missing or not a non-empty string",
            })

    # exports — must be present as an array (high if absent/not-a-list).
    exports = data.get("exports")
    if not isinstance(exports, list):
        required_issues.append({
            "severity": "high",
            "field": "exports",
            "message": "exports missing or not an array",
        })
    elif len(exports) == 0:
        required_issues.append({
            "severity": "low",
            "field": "exports",
            "message": "exports array is empty",
        })

    # Enum membership — only when the value is present as a non-empty string
    # (otherwise the required-field check above already fired for it).
    for field, allowed in _EXPORT_GATE_ENUMS.items():
        val = data.get(field)
        if isinstance(val, str) and val and val not in allowed:
            enum_issues.append({
                "severity": "high",
                "field": field,
                "message": f"{field} '{val}' not in {list(allowed)}",
            })

    return required_issues, enum_issues


def _extract_section_7b_refs(skill_md_text):
    """Extract scripts/… and assets/… paths named in SKILL.md's Section 7b
    (Scripts & Assets). Returns a set of posix path strings.

    Section 7b is optional (create-skill emits it only when scripts or assets
    are detected), so an absent section yields an empty set. The section is
    located by its heading — a markdown heading whose text mentions both
    "script" and "asset" (the "Scripts & Assets" title) — and the region runs
    until the next heading of the same or higher level.
    """
    if not skill_md_text:
        return set()

    lines = skill_md_text.split("\n")
    start = None
    heading_level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            text = m.group(2).lower()
            if "script" in text and "asset" in text:
                start = i + 1
                heading_level = len(m.group(1))
                break

    if start is None:
        return set()

    end = len(lines)
    for j in range(start, len(lines)):
        m = re.match(r"^(#{1,6})\s+", lines[j])
        if m and len(m.group(1)) <= heading_level:
            end = j
            break

    region = "\n".join(lines[start:end])
    refs = set()
    for match in _SECTION_7B_PATH_RE.findall(region):
        refs.add(match.rstrip("./-"))
    return refs


def crossref_section_7b(skill_md_text, pkg_dir):
    """Cross-reference SKILL.md Section 7b against on-disk scripts/ and assets/.

    Returns (missing, orphans) — both sorted lists of posix relative paths
    (e.g. "scripts/run.py"). `missing` = paths named under Section 7b that do
    not exist on disk (a broken manifest — the caller treats these as high).
    `orphans` = scripts/assets files present on disk but not named under
    Section 7b (a low warning). Deterministic: same inputs → same sorted lists.
    """
    pkg_dir = Path(pkg_dir)
    referenced = _extract_section_7b_refs(skill_md_text)

    on_disk = set()
    for sub in ("scripts", "assets"):
        d = pkg_dir / sub
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    on_disk.add(p.relative_to(pkg_dir).as_posix())

    missing = sorted(referenced - on_disk)
    orphans = sorted(on_disk - referenced)
    return missing, orphans


def validate_stack_counts(skill_dir, meta):
    """Validate stack-package count equalities against on-disk reference files.

    Deterministic integer arithmetic the validate.md prompt previously did by
    hand each run:
      - library_count (metadata) == number of per-library reference files
        (references/*.md, excluding the integrations/ subdir and stack-catalog.md)
      - integration_count (metadata) == number of integration pair files
        (references/integrations/*.md)
      - sum(confidence_distribution over t1, t1_low, t2, t3) == library_count

    Returns (issues, observed) where issues use the same {severity, field,
    message} shape as the other validators and observed carries the exact
    counts so the prompt can echo numbers without recomputing them.
    """
    skill_dir = Path(skill_dir)
    references = skill_dir / "references"

    # Per-library reference files: top-level references/*.md.
    # glob("*.md") is non-recursive, so references/integrations/*.md is
    # excluded automatically; stack-catalog.md is excluded by name.
    ref_file_count = 0
    if references.is_dir():
        for p in sorted(references.glob("*.md")):
            if p.name == "stack-catalog.md":
                continue
            ref_file_count += 1

    # Integration pair files: references/integrations/*.md.
    integrations_dir = references / "integrations"
    pair_file_count = 0
    if integrations_dir.is_dir():
        pair_file_count = sum(1 for _ in integrations_dir.glob("*.md"))

    library_count_meta = meta.get("library_count")
    integration_count_meta = meta.get("integration_count")

    dist = meta.get("confidence_distribution")
    confidence_sum = None
    if isinstance(dist, dict):
        confidence_sum = 0
        for key in ("t1", "t1_low", "t2", "t3"):
            val = dist.get(key, 0)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                confidence_sum += val

    observed = {
        "library_count_meta": library_count_meta,
        "ref_file_count": ref_file_count,
        "integration_count_meta": integration_count_meta,
        "pair_file_count": pair_file_count,
        "confidence_sum": confidence_sum,
    }

    def _is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    issues = []

    # library_count vs per-library reference file count
    if _is_int(library_count_meta):
        if library_count_meta != ref_file_count:
            issues.append({
                "severity": "medium",
                "field": "library_count",
                "message": f"library_count ({library_count_meta}) does not match per-library reference file count ({ref_file_count})",
            })
    else:
        issues.append({
            "severity": "medium",
            "field": "library_count",
            "message": "library_count missing or not an integer",
        })

    # integration_count vs integration pair file count
    if _is_int(integration_count_meta):
        if integration_count_meta != pair_file_count:
            issues.append({
                "severity": "medium",
                "field": "integration_count",
                "message": f"integration_count ({integration_count_meta}) does not match integration pair file count ({pair_file_count})",
            })
    else:
        issues.append({
            "severity": "medium",
            "field": "integration_count",
            "message": "integration_count missing or not an integer",
        })

    # confidence_distribution sum vs library_count
    if confidence_sum is None:
        issues.append({
            "severity": "medium",
            "field": "confidence_distribution",
            "message": "confidence_distribution missing or not an object with t1/t1_low/t2/t3 keys",
        })
    elif _is_int(library_count_meta) and confidence_sum != library_count_meta:
        issues.append({
            "severity": "medium",
            "field": "confidence_distribution",
            "message": f"confidence_distribution sum ({confidence_sum}) does not match library_count ({library_count_meta})",
        })

    return issues, observed


def validate_skill_package(skill_dir, generated_by=None, skip_frontmatter=False, skill_type="individual", export_gate=False):
    """Validate a complete skill package directory.

    When `skip_frontmatter` is True, the SKILL.md frontmatter pass is omitted —
    intended for callers that already validated frontmatter via skill-check or
    skf-validate-frontmatter.py and only want body / snippet / metadata checks.

    `skill_type` selects the package schema (default "individual", unchanged for
    existing callers). "stack" skips the individual-skill body-structure and
    metadata-schema passes (which assume the single-skill shape) and instead
    runs validate_stack_counts, emitting validation.stack_counts.{issues,observed}.
    Frontmatter and context-snippet checks are shape-agnostic and run for both.

    When `export_gate` is True, a self-contained export-gate validation runs
    instead (see _validate_export_gate). This branch is additive: the
    individual/stack code below is untouched, so callers that never pass
    export_gate=True get byte-identical output.
    """
    if export_gate:
        return _validate_export_gate(skill_dir)

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
        content = skill_md_path.read_text(encoding="utf-8")
        if skip_frontmatter:
            fm_section = {"skipped": "frontmatter validation skipped (--skip-frontmatter)"}
            fm_issues = []
        else:
            fm_issues = validate_frontmatter(content, skill_name)
            fm_section = fm_issues
        if skill_type == "stack":
            # Individual-skill body sections (Overview/Description/Key Exports/
            # Usage) do not apply to a stack capstone — checked in validate.md §4.
            body_section = {"skipped": "stack-type: individual body-structure check not applicable"}
            body_issues = []
        else:
            body_issues = validate_body_structure(content)
            body_section = body_issues
        result["validation"]["skill_md"] = {"frontmatter": fm_section, "body": body_section}
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
        content = snippet_path.read_text(encoding="utf-8")
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
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if skill_type == "stack":
                # Individual-skill metadata schema (source_repo, stats.*) does not
                # apply to a stack capstone; validate the stack count-equalities.
                result["validation"]["metadata"] = {"skipped": "stack-type: individual metadata schema not checked (see validation.stack_counts)"}
                stack_issues, observed = validate_stack_counts(skill_dir, meta)
                result["validation"]["stack_counts"] = {"issues": stack_issues, "observed": observed}
                for issue in stack_issues:
                    result["summary"]["total_issues"] += 1
                    result["summary"]["by_severity"][issue["severity"]] += 1
            else:
                meta_issues = validate_metadata_json(meta, generated_by)
                result["validation"]["metadata"] = {"issues": meta_issues}
                for issue in meta_issues:
                    result["summary"]["total_issues"] += 1
                    result["summary"]["by_severity"][issue["severity"]] += 1
        except json.JSONDecodeError as e:
            result["validation"]["metadata"] = {"error": f"JSON parse error: {e}"}
            result["summary"]["total_issues"] += 1
            result["summary"]["by_severity"]["high"] += 1
            if skill_type == "stack":
                result["validation"]["stack_counts"] = {"skipped": f"metadata.json parse error: {e}"}
    else:
        result["validation"]["metadata"] = {"skipped": "metadata.json not found"}
        if skill_type == "stack":
            result["validation"]["stack_counts"] = {"skipped": "metadata.json not found"}

    # Overall pass/fail
    result["result"] = "PASS" if result["summary"]["by_severity"]["high"] == 0 else "FAIL"

    return result


def _validate_export_gate(skill_dir):
    """Export-gate validation for skf-export-skill's publishing gate.

    Self-contained: does not run the individual/stack passes. Emits the
    deterministic verdict load-skill.md §2 and package.md §1-3 previously
    derived in-prompt — SKILL.md presence/non-emptiness, metadata.json valid
    JSON + required-field presence + enum membership, and the SKILL.md
    Section 7b <-> on-disk scripts/assets cross-reference — plus a deterministic
    export_status ∈ READY / WARNINGS / NOT_READY.
    """
    skill_dir = Path(skill_dir)
    skill_name = skill_dir.name

    result = {
        "status": "ok",
        "mode": "export-gate",
        "skill_dir": str(skill_dir),
        "skill_name": skill_name,
        "files_found": {},
        "validation": {},
        "summary": {"total_issues": 0, "by_severity": {"high": 0, "medium": 0, "low": 0}},
    }

    def _record(issues):
        for issue in issues:
            result["summary"]["total_issues"] += 1
            result["summary"]["by_severity"][issue["severity"]] += 1

    skill_md_path = skill_dir / "SKILL.md"
    meta_path = skill_dir / "metadata.json"
    result["files_found"]["SKILL.md"] = skill_md_path.exists()
    result["files_found"]["metadata.json"] = meta_path.exists()

    # 1. SKILL.md must exist and be non-empty.
    skill_md_text = ""
    skill_md_issues = []
    if not skill_md_path.exists():
        skill_md_issues.append({"severity": "high", "field": "SKILL.md", "message": "SKILL.md not found"})
    else:
        skill_md_text = skill_md_path.read_text(encoding="utf-8")
        if not skill_md_text.strip():
            skill_md_issues.append({"severity": "high", "field": "SKILL.md", "message": "SKILL.md is empty"})
    result["validation"]["skill_md"] = {"issues": skill_md_issues}
    _record(skill_md_issues)

    # 2. metadata.json must exist, parse as JSON, and satisfy the required-field
    #    presence + enum-membership contract.
    if not meta_path.exists():
        meta_issues = [{"severity": "high", "field": "metadata.json", "message": "metadata.json not found"}]
        result["validation"]["metadata"] = {"issues": meta_issues, "enum_issues": []}
        _record(meta_issues)
    else:
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except json.JSONDecodeError as e:
            meta_issues = [{"severity": "high", "field": "metadata.json", "message": f"JSON parse error: {e}"}]
            result["validation"]["metadata"] = {"issues": meta_issues, "enum_issues": []}
            _record(meta_issues)
        else:
            required_issues, enum_issues = validate_metadata_export_gate(meta)
            result["validation"]["metadata"] = {"issues": required_issues, "enum_issues": enum_issues}
            _record(required_issues)
            _record(enum_issues)

    # 3. SKILL.md Section 7b <-> on-disk scripts/assets cross-reference.
    missing, orphans = crossref_section_7b(skill_md_text, skill_dir)
    crossref_issues = []
    for path in missing:
        crossref_issues.append({
            "severity": "high",
            "field": "crossref_7b",
            "message": f"SKILL.md Section 7b references '{path}' but it is absent on disk",
        })
    for path in orphans:
        crossref_issues.append({
            "severity": "low",
            "field": "crossref_7b",
            "message": f"'{path}' present on disk but not referenced in SKILL.md Section 7b (orphan)",
        })
    result["validation"]["crossref_7b"] = {
        "missing": missing,
        "orphans": orphans,
        "issues": crossref_issues,
    }
    _record(crossref_issues)

    # Deterministic export_status + PASS/FAIL result.
    by_sev = result["summary"]["by_severity"]
    if by_sev["high"] > 0:
        result["export_status"] = "NOT_READY"
    elif by_sev["medium"] > 0 or by_sev["low"] > 0:
        result["export_status"] = "WARNINGS"
    else:
        result["export_status"] = "READY"
    result["result"] = "PASS" if by_sev["high"] == 0 else "FAIL"

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python3 skf-validate-output.py <skill-package-dir> "
            "[--generated-by <generator>] [--skip-frontmatter] "
            "[--skill-type {individual,stack}] [--export-gate]",
            file=sys.stderr,
        )
        sys.exit(1)

    pkg_dir = sys.argv[1]

    # --export-gate is a distinct, self-contained mode (skf-export-skill's
    # publishing gate). It ignores the individual/stack flags below.
    if "--export-gate" in sys.argv:
        result = validate_skill_package(pkg_dir, export_gate=True)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["result"] == "PASS" else 1)

    gen_by = None
    if "--generated-by" in sys.argv:
        idx = sys.argv.index("--generated-by")
        if idx + 1 < len(sys.argv):
            gen_by = sys.argv[idx + 1]

    skip_fm = "--skip-frontmatter" in sys.argv

    skill_type = "individual"
    if "--skill-type" in sys.argv:
        idx = sys.argv.index("--skill-type")
        if idx + 1 < len(sys.argv):
            skill_type = sys.argv[idx + 1]
    if skill_type not in ("individual", "stack"):
        print(
            f"Error: --skill-type must be 'individual' or 'stack', got: {skill_type}",
            file=sys.stderr,
        )
        sys.exit(2)

    result = validate_skill_package(
        pkg_dir, generated_by=gen_by, skip_frontmatter=skip_fm, skill_type=skill_type
    )
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["result"] == "PASS" else 1)
