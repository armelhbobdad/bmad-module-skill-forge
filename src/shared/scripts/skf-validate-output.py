# /// script
# requires-python = ">=3.11"
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
               library_count), emitted under validation.stack_counts, and the
               stack structure, emitted under validation.stack_structure (see
               validate_stack_structure): the SKILL.md headings of the stack
               template with the catalog inline or behind a pointer, a
               citation on each `## Conventions` bullet (low), every
               relative link in SKILL.md and references/stack-catalog.md, the
               metadata.json keys and values with the dominant tier recomputed
               by skf-render-stack-metadata.py beside this script, the headings
               of each reference and pair file and a file for each library and
               pair metadata.json lists, and a tier label on each
               per-library summary, pair entry and reference file. Each of
               its issues names in `check` the create-stack-skill validate.md
               section that records it. --forge-tier <tier> also checks
               metadata.json's forge_tier against the run's tier.

The --export-gate flag selects a third, self-contained mode used by
skf-export-skill's publishing gate (load-skill.md §2 runs it, §3 binds its
`package` object and §5 renders the verdict). It is additive and orthogonal
to --skill-type: it does NOT touch the individual/stack code path above, so
existing callers keep byte-identical output. Under the flag the script emits
the deterministic verdict the export prompt previously derived by hand each
run:
  - metadata.json required-field presence for the full agentskills.io set
    (name, version, skill_type, source_authority, exports, generation_date,
    confidence_tier) as high-severity issues under validation.metadata.issues;
  - enum-membership checks (skill_type, source_authority, confidence_tier) as
    high-severity issues under validation.metadata.enum_issues. The
    confidence_tier set depends on skill_type: a single skill records its
    forge tier (Quick / Forge / Forge+ / Deep), a stack the dominant
    confidence tier of its libraries (T1 / T1-low / T2 / T3). A stack that
    still holds a forge tier there, as older stacks do, passes with a low
    note under validation.metadata.issues;
  - recommended-field presence, chosen by skill_type, as low-severity issues
    under validation.metadata.recommended_missing: description, source_repo,
    language and tool_versions for a single skill (plus ast_node_count when
    confidence_distribution.t1 is above 0), language and tool_versions for a
    stack;
  - SKILL.md Section 7b (Scripts & Assets) cross-reference against on-disk
    scripts/ and assets/ files, under validation.crossref_7b.{missing,orphans}
    (a §7b-named file absent on disk is high; an on-disk file not named in §7b
    is a low orphan warning). Only a path that starts with scripts/ or
    assets/, optionally after ./, is read as a bundled file. The section is
    the level-2 `## Scripts & Assets` heading create-skill writes (optionally
    numbered, as in `## 7b. Scripts & Assets`), found outside fenced code, and
    validation.crossref_7b.{heading,heading_line} name the heading it matched
    and its line (both null when SKILL.md has no Section 7b);
  - a deterministic export_status ∈ READY / WARNINGS / NOT_READY alongside the
    existing PASS/FAIL result (NOT_READY on any high issue, WARNINGS when only
    medium/low issues remain, READY when clean);
  - a `package` object, always present, with the fields load-skill.md's
    confirm screen shows (see export_gate_package): name, version,
    skill_type, source_authority, confidence_tier, forge_tier and
    generation_date as metadata.json holds them; exports_count and
    top_exports (the first 5 names); references_count, the files under
    references/ at any depth, the count skf-count-tokens.py gives as
    references_total.count; and, for a stack, components_count and
    integrations_count. A field metadata.json lacks is null, and every
    field but references_count is null when metadata.json is missing, does
    not parse or is not a JSON object.

The --snippet-check flag selects a fourth mode, which skf-export-skill's
generate-snippet.md §4 runs on each context snippet draft before step 3
lists it in a managed section and copies it into the package. The
positional argument is then the draft folder, which holds
context-snippet.md, and --package names the skill package the draft is
for. It reports `issues`, each {severity, field, message}: first those of
validate_context_snippet (content high for an empty draft, line 1 and
line 2 medium, length low), then these high ones:
  - content:   context-snippet.md is missing, a folder or not UTF-8 text;
  - header:    line 1's `[name vX]` is not the package folder's basename at
               metadata.json's `version`, or metadata.json gives no version;
  - separator: a blank or bare `|` line between the first and last
               non-blank lines (the managed section reads it as the end of
               the row), naming its line;
  - marker:    an SKF marker (`<!-- SKF:BEGIN` or `<!-- SKF:END`);
  - anchor:    a `SKILL.md#slug` or `references/<file>.md#slug` anchor whose
               file is not in the package, whose path has `..`, or whose
               file has no heading with that slug (heading_slugs gives
               GitHub's slugs).
`result` is FAIL on any high or medium issue: exit 0 on PASS, 1 on FAIL.
No --package value, or one that names no folder, prints `error: ...` on
stderr and exits 2. The other modes ignore the flag's absence: their
output is unchanged.

CLI: python3 skf-validate-output.py <skill-package-dir>
     python3 skf-validate-output.py <skill-package-dir> --generated-by quick-skill
     python3 skf-validate-output.py <skill-package-dir> --skip-frontmatter
     python3 skf-validate-output.py <skill-package-dir> --skill-type stack
     python3 skf-validate-output.py <skill-package-dir> --skill-type stack --forge-tier Deep
     python3 skf-validate-output.py <skill-package-dir> --export-gate
     python3 skf-validate-output.py <draft-dir> --snippet-check --package <skill-package-dir>
"""

from __future__ import annotations

import importlib.util
import json
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import unquote


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


# The context snippet's length bounds, in `len(text)//4` tokens. The ceiling is
# the hard 300-token ceiling export-skill's generate-snippet.md §4 sets (a Deep
# snippet may pass the ~80-120 target when its gotchas carry load-bearing
# breaking-change notices), so a snippet that step accepts is never flagged.
SNIPPET_TOKEN_FLOOR = 40
SNIPPET_TOKEN_CEILING = 300


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
    if approx_tokens < SNIPPET_TOKEN_FLOOR:
        issues.append({"severity": "low", "field": "length", "message": f"Context snippet may be too short (~{approx_tokens} tokens)"})
    elif approx_tokens > SNIPPET_TOKEN_CEILING:
        issues.append({"severity": "low", "field": "length",
                       "message": f"Context snippet is above the {SNIPPET_TOKEN_CEILING}-token ceiling (~{approx_tokens} tokens)"})

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
}

# confidence_tier holds a different scale per skill_type: a single skill
# records the forge tier it was compiled at, a stack records the dominant
# confidence tier of its libraries (create-stack-skill keeps the forge tier in
# forge_tier). Older stacks hold their forge tier in confidence_tier (the
# v0.10.0 stack template wrote it there, and stacks on disk still carry it),
# and the gate accepted them before the stack scale existed, so a stack also
# accepts a forge tier: validate_metadata_export_gate adds a low note for it
# instead of failing the export. When skill_type is neither, the value is
# checked against both scales (skill_type itself already fails its enum check).
_FORGE_TIERS = ("Quick", "Forge", "Forge+", "Deep")
_EXPORT_GATE_CONFIDENCE_TIERS = {
    "single": _FORGE_TIERS,
    "stack": ("T1", "T1-low", "T2", "T3") + _FORGE_TIERS,
}

# Recommended (non-required) metadata fields, by skill_type: the fields the
# generator's metadata template always writes (quick-skill and create-skill
# for single, create-stack-skill for stack). A stack's template has no
# description or source_repo, so a stack is never warned about them.
# ast_node_count is written only when ast-grep ran, so a single skill is
# expected to carry it only when confidence_distribution counts T1
# (AST-verified) signatures. A stack is never asked for it: its T1 count is
# inherited from its libraries, not from an AST pass of its own.
_EXPORT_GATE_RECOMMENDED = {
    "single": ("description", "source_repo", "language", "tool_versions"),
    "stack": ("language", "tool_versions"),
}

# Matches a scripts/… or assets/… path token (e.g. `scripts/run.py`) and
# captures it without an optional leading `./`. The match starts only at the
# beginning of a path token, so an upstream path such as
# `bmad-module-builder/scripts/x.py` is not read as the package's own
# `scripts/x.py`. The leading filename char must be alphanumeric/dot/underscore
# so a bare `scripts/` (the §7b directory note with nothing after the slash)
# is not captured as a file reference.
_SECTION_7B_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._/\-])(?:\./)?((?:scripts|assets)/[A-Za-z0-9._][A-Za-z0-9._/\-]*)"
)
# The title of Section 7b's level-2 heading (skf-create-skill/assets/
# skill-sections.md, compile-assembly-rules.md), with an optional section
# number such as `7b.` before it.
_SECTION_7B_TITLE_RE = re.compile(r"^(?:\d+[A-Za-z]?\.?[ \t]+)?Scripts & Assets$", re.IGNORECASE)


def _is_blank(val):
    """True when a metadata value is absent or empty (None, "", [], {})."""
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return not val
    return False


def _counts_t1(data):
    """True when confidence_distribution.t1 is a positive number."""
    dist = data.get("confidence_distribution")
    if not isinstance(dist, dict):
        return False
    t1 = dist.get("t1")
    return isinstance(t1, (int, float)) and not isinstance(t1, bool) and t1 > 0


def validate_metadata_export_gate(data):
    """agentskills.io export-gate metadata validation.

    Returns (required_issues, enum_issues, recommended_missing). Required-field
    presence for the full agentskills.io set is high-severity; enum-membership
    mismatches are high-severity, with the confidence_tier scale chosen by
    skill_type. An empty `exports` array is a low warning (matching
    load-skill.md §2's "warn if empty — graceful handling"), not a hard halt.
    So is a forge tier in a stack's confidence_tier (the value older stacks
    hold); both of these low notes go in required_issues.
    A missing or empty recommended field for the skill_type is a low warning;
    when skill_type is neither single nor stack no recommended set applies.
    """
    required_issues = []
    enum_issues = []
    recommended_missing = []
    skill_type = data.get("skill_type")
    if not isinstance(skill_type, str):
        skill_type = None

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

    tier = data.get("confidence_tier")
    if isinstance(tier, str) and tier:
        if skill_type in _EXPORT_GATE_CONFIDENCE_TIERS:
            allowed = _EXPORT_GATE_CONFIDENCE_TIERS[skill_type]
            scope = f" for skill_type '{skill_type}'"
        else:
            allowed = tuple(dict.fromkeys(
                t for tiers in _EXPORT_GATE_CONFIDENCE_TIERS.values() for t in tiers
            ))
            scope = ""
        if tier not in allowed:
            enum_issues.append({
                "severity": "high",
                "field": "confidence_tier",
                "message": f"confidence_tier '{tier}' not in {list(allowed)}{scope}",
            })
        elif skill_type == "stack" and tier in _FORGE_TIERS:
            required_issues.append({
                "severity": "low",
                "field": "confidence_tier",
                "message": (
                    f"confidence_tier '{tier}' is a forge tier, as older stacks recorded it; "
                    "re-run Stack Skill (@Ferris SS) to record the dominant confidence tier "
                    "of its libraries (T1, T1-low, T2 or T3)"
                ),
            })

    # Recommended fields: low-severity presence checks, by skill_type.
    recommended = list(_EXPORT_GATE_RECOMMENDED.get(skill_type, ()))
    if skill_type == "single" and _counts_t1(data):
        recommended.append("ast_node_count")
    for field in recommended:
        if _is_blank(data.get(field)):
            recommended_missing.append({
                "severity": "low",
                "field": field,
                "message": f"recommended field {field} missing or empty for a {skill_type} skill",
            })

    return required_issues, enum_issues, recommended_missing


# The number of export names the export gate's `package.top_exports` lists.
_EXPORT_GATE_TOP_EXPORTS = 5


def count_reference_files(skill_dir):
    """The number of files under the package's references/ at any depth.

    It walks references/ as skf-count-tokens.py's measure_reference_files
    does (rglob, then is_file), so it equals that script's
    references_total.count. 0 when references/ is absent.
    """
    references = Path(skill_dir) / "references"
    if not references.is_dir():
        return 0
    return sum(1 for path in references.rglob("*") if path.is_file())


def _export_name(item):
    """An exports item's name, or None.

    The item when it is a non-blank string, else a dict item's non-blank
    string `name`.
    """
    if isinstance(item, dict):
        item = item.get("name")
    return item if isinstance(item, str) and item.strip() else None


def _stack_count(data, count_key, list_key):
    """A stack's count: `count_key` when it is an int, else the length of the `list_key` list, else None."""
    count = data.get(count_key)
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    items = data.get(list_key)
    return len(items) if isinstance(items, list) else None


def export_gate_package(meta, references_count):
    """The export gate's `package` object, which load-skill.md §3 binds and §5 renders.

    `meta` is the parsed metadata.json, or None when it is missing, does not
    parse or is not a JSON object: every field but `references_count` is then
    null. A text field is null unless metadata.json holds it as a non-empty
    string, the test validate_metadata_export_gate puts each required field
    to, so a package the gate passes has every required field set.
    `exports_count` is the length of the `exports` array and `top_exports`
    its first 5 names (a non-blank string item, or a dict item's non-blank
    string `name`; another item is skipped), both null when `exports` is not
    an array. A stack's `components_count` is `library_count` when it is an int,
    else the length of `libraries`, and its `integrations_count` is
    `integration_count`, else the length of `integration_pairs`; both are
    null for any other skill_type.
    """
    data = meta if isinstance(meta, dict) else {}

    def text(field):
        val = data.get(field)
        return val if isinstance(val, str) and val else None

    exports = data.get("exports")
    names = None
    if isinstance(exports, list):
        names = [name for name in map(_export_name, exports) if name is not None]
    stack = data.get("skill_type") == "stack"
    return {
        "name": text("name"),
        "version": text("version"),
        "skill_type": text("skill_type"),
        "source_authority": text("source_authority"),
        "confidence_tier": text("confidence_tier"),
        "forge_tier": text("forge_tier"),
        "generation_date": text("generation_date"),
        "exports_count": len(exports) if isinstance(exports, list) else None,
        "top_exports": names[:_EXPORT_GATE_TOP_EXPORTS] if names is not None else None,
        "references_count": references_count,
        "components_count": _stack_count(data, "library_count", "libraries") if stack else None,
        "integrations_count": _stack_count(data, "integration_count", "integration_pairs") if stack else None,
    }


def _section_7b_bounds(skill_md_text):
    """(heading, heading_line, start, end) of SKILL.md's Section 7b, or None.

    Section 7b is the first level-2 heading titled `Scripts & Assets` (the
    heading create-skill writes, optionally numbered as in
    `## 7b. Scripts & Assets`) outside fenced code, and runs until the next
    level-1 or level-2 heading outside fenced code. A heading that only
    mentions scripts and assets (`### Loading assets from JavaScript`) or a
    shell comment inside a code fence is not it. `heading` is the heading
    line as written, `heading_line` its 1-based line number, and `start` and
    `end` slice the section's body out of the text's lines.
    """
    if not skill_md_text:
        return None
    headings = _headings(skill_md_text)
    for k, (level, title, index) in enumerate(headings):
        if level == 2 and _SECTION_7B_TITLE_RE.match(title):
            lines = skill_md_text.split("\n")
            end = next((i for lvl, _, i in headings[k + 1:] if lvl <= 2), len(lines))
            return lines[index].strip(), index + 1, index + 1, end
    return None


def section_7b_heading(skill_md_text):
    """(heading, heading_line) of SKILL.md's Section 7b, or (None, None) when it has none."""
    bounds = _section_7b_bounds(skill_md_text)
    return (bounds[0], bounds[1]) if bounds else (None, None)


def _extract_section_7b_refs(skill_md_text):
    """Extract scripts/… and assets/… paths named in SKILL.md's Section 7b
    (Scripts & Assets). Returns a set of posix path strings.

    Section 7b is optional (create-skill emits it only when scripts or assets
    are detected), so an absent section yields an empty set. _section_7b_bounds
    locates it by its exact heading.
    """
    bounds = _section_7b_bounds(skill_md_text)
    if bounds is None:
        return set()

    _, _, start, end = bounds
    region = "\n".join(skill_md_text.split("\n")[start:end])
    refs = set()
    # findall returns the capture group: the path without a leading `./`.
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


# --- Stack structure pass (--skill-type stack) ------------------------------
#
# The checks create-stack-skill's validate.md §4 to §7 made by hand over every
# file of a committed stack, against src/skf-create-stack-skill/assets/
# stack-skill-template.md and, for metadata.json, assets/metadata-contract.md.
# Each issue carries `check`, the validate.md section
# that records it: skill_md (§4), metadata (§5), references (§6) and
# tier_labels (§7).

# The helper beside this script that holds the stack tier rules.
_STACK_RULES_HELPER = "skf-render-stack-metadata.py"

# The metadata.json keys the stack metadata contract writes, less ast_node_count
# (written only when ast-grep ran) and the three validate_stack_counts checks
# (library_count, integration_count, confidence_distribution).
_STACK_REQUIRED_KEYS = (
    "skill_type", "name", "version", "generation_date", "forge_tier", "confidence_tier",
    "spec_version", "source_authority", "generated_by", "exports", "libraries",
    "integration_pairs", "language", "tool_versions", "stats", "dependencies", "compatibility",
)
_STACK_TIERS = ("T1", "T1-low", "T2", "T3")
_SOURCE_AUTHORITIES = ("official", "community", "internal")
_DISTRIBUTION_KEYS = ("t1", "t1_low", "t2", "t3")

# The SKILL.md and stack-catalog.md headings of the stack template.
_STACK_CATALOG = "references/stack-catalog.md"
_INTEGRATION_PATTERNS = "Integration Patterns"
_PAIR_INTEGRATIONS = "Library Pair Integrations"
_REFERENCE_INDEX = "Library Reference Index"
_PER_LIBRARY = "Per-Library Summaries"
_CATALOG_POINTER = "Library Catalog"
_CONVENTIONS = "Conventions"
# A Conventions bullet's citation: code mode's `(src/app.ts:12)`, several of
# them comma-separated in one pair of parentheses (`(src/app.ts:12, src/b.ts:4)`),
# or compose mode's `[from skill: react]`; the template's `{file}:{line}` and
# `{name}` placeholders are none, nor is text in a code span.
_CITED_LINE = r"[^\s,:{}]+:\d+(?:-\d+)?"
_CONVENTION_CITATION_RE = re.compile(
    rf"\({_CITED_LINE}(?:[ \t]*,[ \t]*{_CITED_LINE})*\)|\[from skill:[ \t]*[^\]\s{{}}][^\]{{}}]*\]")
# A list item's first line: `- `, `* ` or `+ `, or `1. ` or `1) `.
_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+\S")
# The headings of a per-library file and of an integration pair file.
_LIBRARY_FILE_HEADINGS = ("Key Exports", "Usage Patterns")
_PAIR_FILE_HEADINGS = ("Integration Pattern", "Key Files")

# The line under the SKILL.md title: `> 3 libraries | 2 integration patterns | Forge tier: Deep`.
_STACK_HEADER_RE = re.compile(
    r"^>[ \t]*(\d+)[ \t]+librar(?:y|ies)[ \t]*\|[ \t]*(\d+)[ \t]+integration patterns?[ \t]*\|"
    r"[ \t]*Forge tier:[ \t]*([A-Za-z+]+)",
    re.MULTILINE,
)
# A tier label: `**Confidence:**` then a T-code, T1-low tried before T1. It,
# and the `**Version:**` and `**Type:**` lines, may sit in a list item.
_TIER_LABEL_RE = re.compile(r"^(?:[-*+][ \t]+)?\*\*Confidence:\*\*[ \t]*(?:T1-low|T1|T2|T3)(?![\w-])",
                            re.MULTILINE)
_VERSION_LINE_RE = re.compile(r"^(?:[-*+][ \t]+)?\*\*Version:\*\*", re.MULTILINE)
_TYPE_LINE_RE = re.compile(r"^(?:[-*+][ \t]+)?\*\*Type:\*\*", re.MULTILINE)
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
# An inline link or image: the target, bare or in angle brackets, then an optional title.
_LINK_RE = re.compile(r"\]\(\s*(<[^>\n]*>|[^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _stack_rules():
    """The tier rules of skf-render-stack-metadata.py beside this script, or None."""
    path = Path(__file__).resolve().parent / _STACK_RULES_HELPER
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("skf_render_stack_metadata_rules", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (ImportError, OSError, SyntaxError):
        return None
    return module if callable(getattr(module, "dominant_tier", None)) else None


def _markdown_lines(text):
    """(line, is_code) for each line; fence lines and fenced lines are code."""
    out, fence = [], None
    for line in text.split("\n"):
        m = _FENCE_LINE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                out.append((line, True))
                continue
            out.append((line, False))
        else:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line.strip()[len(m.group(1)):]:
                fence = None
            out.append((line, True))
    return out


def _headings(text):
    """[(level, text, line_index)] of the ATX headings outside fenced code, a
    closing run of hashes (`## Conventions ##`) removed."""
    found = []
    for i, (line, code) in enumerate(_markdown_lines(text)):
        m = None if code else _ATX_HEADING_RE.match(line)
        if m:
            body = m.group(2).rstrip(" \t")
            bare = body.rstrip("#")
            if bare != body and (not bare or bare[-1] in " \t"):
                body = bare
            found.append((len(m.group(1)), body.strip(), i))
    return found


def _find_heading(headings, level, name):
    """The first heading of `level` named `name` (case-insensitive), or None."""
    for heading in headings:
        if heading[0] == level and heading[1].lower() == name.lower():
            return heading
    return None


def _block(text, headings, heading):
    """The lines under `heading` up to the next heading of its level or higher."""
    lines = text.split("\n")
    level, _, start = heading
    end = len(lines)
    for other in headings:
        if other[2] > start and other[0] <= level:
            end = other[2]
            break
    return "\n".join(lines[start + 1:end])


def _entries(text, headings, parent, level):
    """[(name, block)] for each heading of `level` inside the `parent` heading's section."""
    section_end = len(text.split("\n"))
    for other in headings:
        if other[2] > parent[2] and other[0] <= parent[0]:
            section_end = other[2]
            break
    return [
        (heading[1], _block(text, headings, heading))
        for heading in headings
        if heading[0] == level and parent[2] < heading[2] < section_end
    ]


def _list_items(text):
    """Each list item outside fenced code, as its first line joined to the lines
    that continue it: a line indented past its marker (a nested bullet, or a
    paragraph after a blank line) or an unindented line before any blank line.
    A fence, a heading, or an unindented line after a blank line ends an item."""
    items, current, indent, blank = [], None, 0, False
    for line, code in _markdown_lines(text):
        if not line.strip() and not code:
            blank = True
            continue
        depth = len(line) - len(line.lstrip(" \t"))
        if code or _ATX_HEADING_RE.match(line):
            current = None
        elif current is not None and depth > indent:
            current.append(line.strip())
        elif _LIST_ITEM_RE.match(line):
            current, indent = [line.strip()], depth
            items.append(current)
        elif current is not None and not blank:
            current.append(line.strip())
        else:
            current = None
        blank = False
    return [" ".join(item) for item in items]


def _header_region(text):
    """A reference file's header: the text before its first `## ` heading."""
    for level, _, index in _headings(text):
        if level == 2:
            return "\n".join(text.split("\n")[:index])
    return text


def _relative_links(text):
    """Each relative link target outside fenced code and inline code: no URL,
    no in-file anchor, no absolute path; `#fragment` and `?query` removed."""
    targets = []
    for line, code in _markdown_lines(text):
        if code:
            continue
        for match in _LINK_RE.finditer(_INLINE_CODE_RE.sub("", line)):
            target = match.group(1)
            if target.startswith("<"):
                target = target[1:-1].strip()
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if target and not target.startswith("/") and not _URL_SCHEME_RE.match(target):
                targets.append(target)
    return targets


def validate_stack_structure(skill_dir, meta, generated_by=None, forge_tier=None):
    """Validate a stack package against the stack template's structure.

    `meta` is the parsed metadata.json, or None when it is missing or does not
    parse (the metadata checks are then skipped). Checks, by `check`:
      - skill_md: a title (H1) and the `> N libraries | M integration
        patterns | Forge tier: T` line under it, its numbers and tier equal
        to metadata.json's; `## Integration Patterns` (unless
        integration_count is 0) ahead of the per-library summaries;
        `## Conventions`, each of its list items outside fenced code citing
        `({file}:{line})` (several comma-separated in one pair of
        parentheses) or `[from skill: {name}]` (low, field `conventions`);
        the catalog inline (`## Library Reference Index`
        and `## Per-Library Summaries`) or behind a `## Library Catalog`
        pointer that links references/stack-catalog.md, which holds both
        sections; every relative link in SKILL.md and stack-catalog.md
        resolving from the file that holds it.
      - metadata: the metadata contract's keys (less ast_node_count and the three
        validate_stack_counts checks); skill_type `stack`; name equal to the
        package folder's; version and generation_date non-empty strings;
        forge_tier a forge tier (and `forge_tier` when given);
        confidence_tier a T-code equal to the dominant tier
        skf-render-stack-metadata.py recomputes from confidence_distribution;
        source_authority an authority; generated_by equal to `generated_by`
        when given (low); exports an array; libraries a non-empty array of
        distinct names, as many as library_count; integration_pairs pairs of
        two different listed libraries, each once, as many as
        integration_count; confidence_distribution holding each of t1,
        t1_low, t2 and t3 as a whole number.
      - references: each references/{library}.md has a title, a
        `**Version:**` line, `## Key Exports` and `## Usage Patterns`; each
        references/integrations/{pair}.md a title, a `**Type:**` line,
        `## Integration Pattern` and `## Key Files`; and, with a readable
        metadata.json, each library `libraries` lists has its
        references/{library}.md and each pair `integration_pairs` lists its
        references/integrations/{a}-{b}.md (or {b}-{a}.md).
      - tier_labels: a `**Confidence:**` T-code label on each entry of the
        per-library summaries (SKILL.md or stack-catalog.md), on each entry
        of `### Library Pair Integrations`, and in the header of each
        reference and pair file.

    Returns (issues, observed). Every issue is medium, except a generated_by
    mismatch, a dominant tier that could not be recomputed and an uncited
    Conventions bullet (low).
    """
    skill_dir = Path(skill_dir)
    references = skill_dir / "references"
    issues = []
    observed = {
        "catalog": None,
        "dominant_tier": None,
        "tier_rule": None,
        "reference_files": 0,
        "pair_files": 0,
        "links_checked": 0,
        "tier_labels_checked": 0,
    }

    def add(check, field, message, severity="medium"):
        issues.append({"severity": severity, "check": check, "field": field, "message": message})

    def read(path, check):
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            rel = path.relative_to(skill_dir).as_posix()
            add(check, rel, f"cannot read {rel}: {exc}")
            return None

    meta = meta if isinstance(meta, dict) else None

    def count(key):
        value = meta.get(key) if meta is not None else None
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def check_links(text, holder, name):
        for target in _relative_links(text):
            observed["links_checked"] += 1
            try:
                resolves = (holder / target).exists()
            except (OSError, ValueError):  # a name the file system cannot hold
                resolves = False
            if not resolves:
                add("skill_md", "link", f"{name} links `{target}`, which does not resolve from {name}'s folder")

    def has_file(folder, name):
        try:
            return (folder / name).is_file()
        except (OSError, ValueError):  # a name the file system cannot hold
            return False

    # --- SKILL.md (§4) and its tier labels (§7) ----------------------------
    skill_md_path = skill_dir / "SKILL.md"
    skill_md = read(skill_md_path, "skill_md") if skill_md_path.is_file() else None
    catalog_text = None
    if skill_md is not None:
        headings = _headings(skill_md)
        if not any(level == 1 for level, _, _ in headings):
            add("skill_md", "heading", "SKILL.md has no title (`# {project_name} Stack Skill`)")
        header = _STACK_HEADER_RE.search(skill_md)
        if header is None:
            add("skill_md", "header", "SKILL.md has no `> {lib_count} libraries | {integration_count} integration "
                "patterns | Forge tier: {tier}` line under its title")
        elif meta is not None:
            for value, key in ((int(header.group(1)), "library_count"), (int(header.group(2)), "integration_count")):
                if count(key) is not None and value != count(key):
                    add("skill_md", "header", f"the SKILL.md header line gives {value} for {key}; metadata.json "
                        f"has {count(key)}")
            if isinstance(meta.get("forge_tier"), str) and header.group(3) != meta["forge_tier"]:
                add("skill_md", "header", f"the SKILL.md header line gives forge tier {header.group(3)}; "
                    f"metadata.json has {meta['forge_tier']}")

        patterns = _find_heading(headings, 2, _INTEGRATION_PATTERNS)
        if patterns is None and count("integration_count") != 0:
            add("skill_md", "heading", f"SKILL.md has no `## {_INTEGRATION_PATTERNS}` section")
        conventions = _find_heading(headings, 2, _CONVENTIONS)
        if conventions is None:
            add("skill_md", "heading", f"SKILL.md has no `## {_CONVENTIONS}` section")
        else:
            for item in _list_items(_block(skill_md, headings, conventions)):
                if not _CONVENTION_CITATION_RE.search(_INLINE_CODE_RE.sub("", item)):
                    add("skill_md", "conventions", f'the `## {_CONVENTIONS}` bullet "{item}" cites no '
                        "`({file}:{line})` or `[from skill: {name}]`", severity="low")

        index = _find_heading(headings, 2, _REFERENCE_INDEX)
        summaries = _find_heading(headings, 2, _PER_LIBRARY)
        pointer = _find_heading(headings, 2, _CATALOG_POINTER)
        summaries_holder = None  # (text, headings, heading, file name)
        if index and summaries:
            observed["catalog"] = "inline"
            summaries_holder = (skill_md, headings, summaries, "SKILL.md")
        elif pointer:
            observed["catalog"] = "pointer"
            links = [posixpath.normpath(t) for t in _relative_links(_block(skill_md, headings, pointer))]
            if _STACK_CATALOG not in links:
                add("skill_md", "catalog", f"the `## {_CATALOG_POINTER}` pointer does not link `{_STACK_CATALOG}`")
            catalog_path = skill_dir / _STACK_CATALOG
            if not catalog_path.is_file():
                add("skill_md", "catalog", f"the `## {_CATALOG_POINTER}` pointer's `{_STACK_CATALOG}` does not exist")
            else:
                catalog_text = read(catalog_path, "skill_md")
                if catalog_text is not None:
                    catalog_headings = _headings(catalog_text)
                    for name in (_REFERENCE_INDEX, _PER_LIBRARY):
                        if _find_heading(catalog_headings, 2, name) is None:
                            add("skill_md", "catalog", f"`{_STACK_CATALOG}` has no `## {name}` section")
                    catalog_summaries = _find_heading(catalog_headings, 2, _PER_LIBRARY)
                    if catalog_summaries:
                        summaries_holder = (catalog_text, catalog_headings, catalog_summaries, "stack-catalog.md")
        else:
            missing = [f"`## {name}`" for name, found in ((_REFERENCE_INDEX, index), (_PER_LIBRARY, summaries))
                       if not found]
            add("skill_md", "catalog", f"SKILL.md has neither the inline catalog (no {' or '.join(missing)}) nor a "
                f"`## {_CATALOG_POINTER}` pointer to `{_STACK_CATALOG}`")

        first_summary = summaries if observed["catalog"] == "inline" else pointer
        if patterns and first_summary and first_summary[2] < patterns[2]:
            add("skill_md", "heading", f"`## {_INTEGRATION_PATTERNS}` comes after the per-library summaries")

        check_links(skill_md, skill_dir, "SKILL.md")
        if catalog_text is not None:
            check_links(catalog_text, references, "stack-catalog.md")

        # Tier labels: each per-library summary and each pair entry.
        if summaries_holder is not None:
            text, holder_headings, heading, name = summaries_holder
            for entry, block in _entries(text, holder_headings, heading, 3):
                observed["tier_labels_checked"] += 1
                if not _TIER_LABEL_RE.search(block):
                    add("tier_labels", "tier_label",
                        f"the per-library summary `### {entry}` in {name} has no `**Confidence:**` T-code label")
        pairs_heading = _find_heading(headings, 3, _PAIR_INTEGRATIONS)
        if patterns and pairs_heading is None and (count("integration_count") or 0) > 0:
            add("skill_md", "heading", f"`## {_INTEGRATION_PATTERNS}` has no `### {_PAIR_INTEGRATIONS}` section")
        if patterns and pairs_heading and pairs_heading[2] > patterns[2]:
            for entry, block in _entries(skill_md, headings, pairs_heading, 4):
                observed["tier_labels_checked"] += 1
                if not _TIER_LABEL_RE.search(block):
                    add("tier_labels", "tier_label",
                        f"the pair entry `#### {entry}` in SKILL.md has no `**Confidence:**` T-code label")

    # --- Reference and pair files (§6) and their tier labels (§7) -------------
    ref_files = []
    if references.is_dir():
        ref_files = [p for p in sorted(references.glob("*.md")) if p.name != "stack-catalog.md"]
    pair_dir = references / "integrations"
    pair_files = sorted(pair_dir.glob("*.md")) if pair_dir.is_dir() else []
    for files, kind, line_re, line_name, required in (
        (ref_files, "reference_files", _VERSION_LINE_RE, "**Version:**", _LIBRARY_FILE_HEADINGS),
        (pair_files, "pair_files", _TYPE_LINE_RE, "**Type:**", _PAIR_FILE_HEADINGS),
    ):
        for path in files:
            observed[kind] += 1
            rel = path.relative_to(skill_dir).as_posix()
            text = read(path, "references")
            if text is None:
                continue
            headings = _headings(text)
            if not any(level == 1 for level, _, _ in headings):
                add("references", rel, f"{rel} has no title (`# ...`)")
            if not line_re.search(text):
                add("references", rel, f"{rel} has no `{line_name}` line")
            for name in required:
                if _find_heading(headings, 2, name) is None:
                    add("references", rel, f"{rel} has no `## {name}` section")
            observed["tier_labels_checked"] += 1
            if not _TIER_LABEL_RE.search(_header_region(text)):
                add("tier_labels", "tier_label", f"{rel} has no `**Confidence:**` T-code label in its header")

    # --- metadata.json (§5) ---------------------------------------------------
    if meta is not None:
        for key in _STACK_REQUIRED_KEYS:
            if key not in meta:
                add("metadata", key, f"metadata.json has no `{key}`")
        if "skill_type" in meta and meta["skill_type"] != "stack":
            add("metadata", "skill_type", f"skill_type is {meta['skill_type']!r}, not 'stack'")
        if "name" in meta and meta["name"] != skill_dir.name:
            add("metadata", "name", f"name {meta['name']!r} does not match the package folder {skill_dir.name!r}")
        for key in ("version", "generation_date"):
            if key in meta and (not isinstance(meta[key], str) or not meta[key].strip()):
                add("metadata", key, f"{key} must be a non-empty string")
        tier = meta.get("forge_tier")
        if "forge_tier" in meta and tier not in _FORGE_TIERS:
            add("metadata", "forge_tier", f"forge_tier {tier!r} not in {list(_FORGE_TIERS)}")
        elif forge_tier is not None and "forge_tier" in meta and tier != forge_tier:
            add("metadata", "forge_tier", f"forge_tier {tier!r} is not this run's forge tier {forge_tier!r}")
        confidence_tier = meta.get("confidence_tier")
        if "confidence_tier" in meta and confidence_tier not in _STACK_TIERS:
            add("metadata", "confidence_tier", f"confidence_tier {confidence_tier!r} not in {list(_STACK_TIERS)}")
        rules = _stack_rules()
        if rules is None:
            add("metadata", "confidence_tier", f"the dominant tier was not recomputed: {_STACK_RULES_HELPER} is not "
                "beside skf-validate-output.py (re-install SKF)", severity="low")
        elif isinstance(meta.get("confidence_distribution"), dict):
            observed["tier_rule"] = _STACK_RULES_HELPER
            observed["dominant_tier"] = rules.dominant_tier(meta["confidence_distribution"])
            if confidence_tier in _STACK_TIERS and confidence_tier != observed["dominant_tier"]:
                add("metadata", "confidence_tier", f"confidence_tier {confidence_tier!r} is not the dominant tier of "
                    f"confidence_distribution ({observed['dominant_tier']!r})")
        authority = meta.get("source_authority")
        if "source_authority" in meta and authority not in _SOURCE_AUTHORITIES:
            add("metadata", "source_authority", f"source_authority {authority!r} not in {list(_SOURCE_AUTHORITIES)}")
        if generated_by and "generated_by" in meta and meta["generated_by"] != generated_by:
            add("metadata", "generated_by", f"generated_by is {meta['generated_by']!r}, expected {generated_by!r}",
                severity="low")
        if "exports" in meta and not isinstance(meta["exports"], list):
            add("metadata", "exports", "exports must be an array (a stack's is empty)")

        libraries = meta.get("libraries")
        names = []
        if "libraries" in meta:
            if (not isinstance(libraries, list) or not libraries
                    or not all(isinstance(n, str) and n.strip() for n in libraries)):
                add("metadata", "libraries", "libraries must be a non-empty array of library names")
            else:
                names = libraries
                if len(set(names)) != len(names):
                    add("metadata", "libraries", "libraries names a library twice")
                if count("library_count") is not None and len(names) != count("library_count"):
                    add("metadata", "libraries", f"libraries lists {len(names)} libraries; library_count is "
                        f"{count('library_count')}")
        pairs = meta.get("integration_pairs")
        listed_pairs = []  # each well-formed pair once, for the file check below
        if "integration_pairs" in meta:
            if not isinstance(pairs, list):
                add("metadata", "integration_pairs", "integration_pairs must be an array of [library, library] pairs")
            else:
                seen = set()
                for i, pair in enumerate(pairs):
                    if (not isinstance(pair, list) or len(pair) != 2
                            or not all(isinstance(n, str) for n in pair) or pair[0] == pair[1]):
                        add("metadata", "integration_pairs",
                            f"integration_pairs[{i}] must be two different library names; got {pair!r}")
                        continue
                    if names and not set(pair) <= set(names):
                        add("metadata", "integration_pairs",
                            f"integration_pairs[{i}] names a library libraries does not list: {pair!r}")
                    if frozenset(pair) in seen:
                        add("metadata", "integration_pairs", f"integration_pairs lists {pair!r} twice")
                    else:
                        listed_pairs.append(pair)
                    seen.add(frozenset(pair))
                if count("integration_count") is not None and len(pairs) != count("integration_count"):
                    add("metadata", "integration_pairs", f"integration_pairs lists {len(pairs)} pairs; "
                        f"integration_count is {count('integration_count')}")
        distribution = meta.get("confidence_distribution")
        if isinstance(distribution, dict):
            for key in _DISTRIBUTION_KEYS:
                value = distribution.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    add("metadata", "confidence_distribution",
                        f"confidence_distribution.{key} must be a whole number; got {value!r}")

        # Each library and pair metadata.json lists has a file of its own
        # (§6), so a misnamed file is caught even when the counts agree.
        for name in dict.fromkeys(names):
            if not has_file(references, f"{name}.md"):
                add("references", f"references/{name}.md",
                    f"libraries lists {name!r}, but references/{name}.md does not exist")
        for a, b in listed_pairs:
            if not (has_file(pair_dir, f"{a}-{b}.md") or has_file(pair_dir, f"{b}-{a}.md")):
                add("references", f"references/integrations/{a}-{b}.md",
                    f"integration_pairs lists {a!r} + {b!r}, but references/integrations/{a}-{b}.md does not exist")

    return issues, observed


def validate_skill_package(skill_dir, generated_by=None, skip_frontmatter=False, skill_type="individual", export_gate=False,
                           forge_tier=None):
    """Validate a complete skill package directory.

    When `skip_frontmatter` is True, the SKILL.md frontmatter pass is omitted —
    intended for callers that already validated frontmatter via skill-check or
    skf-validate-frontmatter.py and only want body / snippet / metadata checks.

    `skill_type` selects the package schema (default "individual", unchanged for
    existing callers). "stack" skips the individual-skill body-structure and
    metadata-schema passes (which assume the single-skill shape) and instead
    runs validate_stack_counts, emitting validation.stack_counts.{issues,observed},
    and validate_stack_structure, emitting validation.stack_structure.{issues,observed}
    (`forge_tier`, when given, is the run's tier metadata.json must record).
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
    stack_meta = None  # the parsed metadata.json object the stack structure pass reads
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if skill_type == "stack" and not isinstance(meta, dict):
                # Valid JSON that is not an object (e.g. `[]`) has no fields to read.
                result["validation"]["metadata"] = {"error": "metadata.json is not a JSON object"}
                result["validation"]["stack_counts"] = {"skipped": "metadata.json is not a JSON object"}
                result["summary"]["total_issues"] += 1
                result["summary"]["by_severity"]["high"] += 1
            elif skill_type == "stack":
                # Individual-skill metadata schema (source_repo, stats.*) does not
                # apply to a stack capstone; validate the stack count-equalities.
                result["validation"]["metadata"] = {"skipped": "stack-type: individual metadata schema not checked (see validation.stack_counts)"}
                stack_meta = meta
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

    # Stack structure: SKILL.md, reference files and tier labels run without
    # a readable metadata.json; its own checks need one.
    if skill_type == "stack":
        structure_issues, observed = validate_stack_structure(skill_dir, stack_meta, generated_by, forge_tier)
        result["validation"]["stack_structure"] = {"issues": structure_issues, "observed": observed}
        for issue in structure_issues:
            result["summary"]["total_issues"] += 1
            result["summary"]["by_severity"][issue["severity"]] += 1

    # Overall pass/fail
    result["result"] = "PASS" if result["summary"]["by_severity"]["high"] == 0 else "FAIL"

    return result


def _validate_export_gate(skill_dir):
    """Export-gate validation for skf-export-skill's publishing gate.

    Self-contained: does not run the individual/stack passes. Emits the
    deterministic verdict load-skill.md §2 and §5 previously derived
    in-prompt: SKILL.md presence/non-emptiness; metadata.json as a valid JSON
    object, with required-field presence and enum membership;
    recommended-field presence by skill_type (low,
    validation.metadata.recommended_missing); and the SKILL.md Section 7b <->
    on-disk scripts/assets cross-reference. It adds a deterministic
    export_status ∈ READY / WARNINGS / NOT_READY, and the `package` object
    load-skill.md §3 binds (export_gate_package).
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

    # 2. metadata.json must exist, parse as a JSON object, and satisfy the
    #    required-field presence + enum-membership contract; missing
    #    recommended fields for its skill_type are low warnings.
    meta_object = None
    if not meta_path.exists():
        meta_issues = [{"severity": "high", "field": "metadata.json", "message": "metadata.json not found"}]
        result["validation"]["metadata"] = {"issues": meta_issues, "enum_issues": [], "recommended_missing": []}
        _record(meta_issues)
    else:
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except json.JSONDecodeError as e:
            meta_issues = [{"severity": "high", "field": "metadata.json", "message": f"JSON parse error: {e}"}]
            result["validation"]["metadata"] = {"issues": meta_issues, "enum_issues": [], "recommended_missing": []}
            _record(meta_issues)
        else:
            if isinstance(meta, dict):
                meta_object = meta
                required_issues, enum_issues, recommended_missing = validate_metadata_export_gate(meta)
            else:
                # Valid JSON that is not an object (e.g. `[]`) has no fields to read.
                required_issues = [{"severity": "high", "field": "metadata.json", "message": "metadata.json is not a JSON object"}]
                enum_issues, recommended_missing = [], []
            result["validation"]["metadata"] = {
                "issues": required_issues,
                "enum_issues": enum_issues,
                "recommended_missing": recommended_missing,
            }
            _record(required_issues)
            _record(enum_issues)
            _record(recommended_missing)

    # 3. SKILL.md Section 7b <-> on-disk scripts/assets cross-reference. The
    #    heading the section was found by, and its line, go in the verdict, so
    #    a halt on a missing file shows which heading named it.
    missing, orphans = crossref_section_7b(skill_md_text, skill_dir)
    heading, heading_line = section_7b_heading(skill_md_text)
    crossref_issues = []
    for path in missing:
        crossref_issues.append({
            "severity": "high",
            "field": "crossref_7b",
            "message": (f"SKILL.md Section 7b ('{heading}' at line {heading_line}) references '{path}' "
                        "but it is absent on disk"),
        })
    for path in orphans:
        crossref_issues.append({
            "severity": "low",
            "field": "crossref_7b",
            "message": f"'{path}' present on disk but not referenced in SKILL.md Section 7b (orphan)",
        })
    result["validation"]["crossref_7b"] = {
        "heading": heading,
        "heading_line": heading_line,
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

    # 4. The fields load-skill.md's confirm screen shows, read once here.
    result["package"] = export_gate_package(meta_object, count_reference_files(skill_dir))

    return result


# --- Snippet-check mode (skf-export-skill generate-snippet.md §4) ----------
#
# Additive like --export-gate: nothing above calls these helpers.

SNIPPET_FILE = "context-snippet.md"
# A snippet's row header, as skf-rebuild-managed-sections.py reads it: `[name vX]`
# at the start of line 1, optionally after the managed section's leading `|`.
_SNIPPET_HEADER_RE = re.compile(r"^\|?\[(?P<name>[^\]]+?) v(?P<version>[^\]\s]+)\]")
# Any SKF marker variant the managed-section writer refuses in a body.
_SNIPPET_MARKER_RE = re.compile(r"<!--\s*SKF:(BEGIN|END)")
# A section anchor of the snippet format: `SKILL.md#slug` or `references/<file>.md#slug`.
# A slug holds only letters, digits, `-` and `_`, so the `}` of the template's
# `{SKILL.md#quick-start}` or a sentence's closing `.` is not part of it.
_SNIPPET_ANCHOR_RE = re.compile(r"(?<![\w./-])(SKILL\.md|references/[^\s#|,;()\[\]`'\"]+?\.md)#([\w-]+)")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def heading_slugs(text):
    """GitHub's anchor slug of each ATX heading outside fenced code and frontmatter, in order.

    The heading text lowercased, each character that is not a letter, digit,
    space, `-` or `_` dropped, each space made `-`; the second heading with
    the same slug takes `-1`, the third `-2`.
    """
    m = _FRONTMATTER_RE.match(text)
    if m:
        text = "\n" * m.group(0).count("\n") + text[m.end():]
    seen, slugs = {}, []
    for _, heading, _ in _headings(text):
        base = "".join(ch for ch in heading.lower() if ch.isalnum() or ch in " -_").replace(" ", "-")
        n = seen.get(base, 0)
        slugs.append(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return slugs


def _package_version(package_dir):
    """metadata.json's `version` when it is a non-empty string, else None."""
    try:
        meta = json.loads((Path(package_dir) / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = meta.get("version") if isinstance(meta, dict) else None
    return version if isinstance(version, str) and version.strip() else None


def _anchor_issue(package_dir, rel, slug, cache):
    """The message of an anchor that does not resolve in the package, or None."""
    if ".." in rel.split("/"):
        return f"{rel}#{slug}: the path leaves the package (`..`)"
    target = Path(package_dir) / rel
    if rel not in cache:
        try:
            cache[rel] = heading_slugs(target.read_text(encoding="utf-8")) if target.is_file() else None
        except (OSError, UnicodeDecodeError):
            cache[rel] = None
    if cache[rel] is None:
        return f"{rel}#{slug}: {rel} is not a file of the package"
    if slug not in cache[rel]:
        return f"{rel}#{slug}: {rel} has no heading whose slug is {slug}"
    return None


def check_snippet_draft(draft_dir, package_dir):
    """Check a staged context-snippet.md draft against the package it is for.

    See the module docstring (--snippet-check) for each check. Returns the
    result object; `result` is FAIL on any high or medium issue.
    """
    draft_dir, package_dir = Path(draft_dir), Path(package_dir)
    skill_name = package_dir.name
    version = _package_version(package_dir)
    issues = []

    snippet = draft_dir / SNIPPET_FILE
    content = None
    if not snippet.is_file():
        what = "a folder" if snippet.is_dir() else "missing"
        issues.append({"severity": "high", "field": "content", "message": f"{snippet.as_posix()} is {what}"})
    else:
        try:
            content = snippet.read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            issues.append({"severity": "high", "field": "content",
                           "message": f"{snippet.as_posix()} is not UTF-8 text ({e})"})
        except OSError as e:
            issues.append({"severity": "high", "field": "content", "message": f"cannot read {snippet.as_posix()}: {e}"})

    if content is not None:
        issues += validate_context_snippet(content)
    if content is not None and content.strip():
        lines = content.split("\n")
        filled = [i for i, line in enumerate(lines) if line.strip()]
        first, last = filled[0], filled[-1]
        header = _SNIPPET_HEADER_RE.match(lines[first].strip())
        if version is None:
            issues.append({"severity": "high", "field": "header",
                           "message": f"metadata.json of {skill_name} gives no version, so line 1 cannot be checked"})
        elif not header or (header.group("name"), header.group("version")) != (skill_name, version):
            issues.append({"severity": "high", "field": "header",
                           "message": f"line 1 must start with [{skill_name} v{version}], got: {lines[first].strip()[:60]}"})
        for i in range(first + 1, last):
            if lines[i].strip() in ("", "|"):
                issues.append({"severity": "high", "field": "separator",
                               "message": f"line {i + 1} is blank or a bare `|`: remove it, since the managed "
                                          "section reads it as the end of the row"})
        if _SNIPPET_MARKER_RE.search(content):
            issues.append({"severity": "high", "field": "marker",
                           "message": "the snippet holds an SKF marker (<!-- SKF:BEGIN or <!-- SKF:END)"})
        cache = {}
        for m in _SNIPPET_ANCHOR_RE.finditer(content):
            message = _anchor_issue(package_dir, m.group(1), m.group(2), cache)
            if message:
                issues.append({"severity": "high", "field": "anchor", "message": message})

    by_severity = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        by_severity[issue["severity"]] += 1
    return {
        "status": "ok",
        "mode": "snippet-check",
        "draft": str(draft_dir),
        "package": str(package_dir),
        "skill_name": skill_name,
        "version": version,
        "issues": issues,
        "summary": {"total_issues": len(issues), "by_severity": by_severity},
        "result": "FAIL" if by_severity["high"] or by_severity["medium"] else "PASS",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python3 skf-validate-output.py <skill-package-dir> "
            "[--generated-by <generator>] [--skip-frontmatter] "
            "[--skill-type {individual,stack}] [--forge-tier <tier>] [--export-gate]\n"
            "       python3 skf-validate-output.py <draft-dir> --snippet-check --package <skill-package-dir>",
            file=sys.stderr,
        )
        sys.exit(1)

    pkg_dir = sys.argv[1]

    # --snippet-check reads a snippet draft folder and the package it is for
    # (skf-export-skill's generate-snippet.md §4); --package is read by index,
    # as --generated-by is.
    if "--snippet-check" in sys.argv:
        package = None
        if "--package" in sys.argv:
            idx = sys.argv.index("--package")
            if idx + 1 < len(sys.argv):
                package = sys.argv[idx + 1]
        if package is None:
            print("error: --snippet-check needs --package <skill-package-dir>", file=sys.stderr)
            sys.exit(2)
        if not Path(package).is_dir():
            print(f"error: --package {package} is not a folder", file=sys.stderr)
            sys.exit(2)
        result = check_snippet_draft(pkg_dir, package)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["result"] == "PASS" else 1)

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

    run_forge_tier = None
    if "--forge-tier" in sys.argv:
        idx = sys.argv.index("--forge-tier")
        if idx + 1 < len(sys.argv):
            run_forge_tier = sys.argv[idx + 1]

    result = validate_skill_package(
        pkg_dir, generated_by=gen_by, skip_frontmatter=skip_fm, skill_type=skill_type,
        forge_tier=run_forge_tier,
    )
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["result"] == "PASS" else 1)
