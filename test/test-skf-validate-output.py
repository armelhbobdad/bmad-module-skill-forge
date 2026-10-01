#!/usr/bin/env python3
"""Tests for skf-validate-output.py."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import importlib.util
import pytest

SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-validate-output.py"
spec = importlib.util.spec_from_file_location("skf_validate_output", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_skill_package = mod.validate_skill_package
validate_stack_counts = mod.validate_stack_counts
validate_stack_structure = mod.validate_stack_structure
validate_metadata_export_gate = mod.validate_metadata_export_gate
crossref_section_7b = mod.crossref_section_7b

VALID_SKILL_MD = """---
name: test-skill
description: A test skill for validation
---

# test-skill

## Overview

Test skill overview with package info.

## Key Exports

- `foo()` — does foo

## Usage Patterns

```js
import { foo } from 'test-skill'
```
"""

VALID_SNIPPET = "[test-skill v1.0.0]|root: skills/test-skill/\n|IMPORTANT: Use this for testing\n|exports: foo, bar\n"

VALID_METADATA = {
    "name": "test-skill",
    "version": "1.0.0",
    "source_authority": "community",
    "source_repo": "https://github.com/test/test-skill",
    "language": "TypeScript",
    "generated_by": "quick-skill",
    "generation_date": "2026-04-08",
    "confidence_tier": "Quick",
    "stats": {
        "exports_documented": 5,
        "exports_public_api": 5,
        "exports_total": 5,
        "public_api_coverage": 1.0,
        "total_coverage": 1.0,
    },
}


def make_valid_package(tmpdir, name="test-skill"):
    pkg = Path(tmpdir) / name
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(VALID_SKILL_MD.replace("test-skill", name), encoding="utf-8")
    (pkg / "context-snippet.md").write_text(VALID_SNIPPET.replace("test-skill", name), encoding="utf-8")
    meta = dict(VALID_METADATA)
    meta["name"] = name
    (pkg / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return pkg


class TestSkfValidateOutput:
    """Tests for the skf-validate-output validate_skill_package function."""

    def test_valid_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp)
            r = validate_skill_package(str(pkg))
            assert r["result"] == "PASS"
            assert r["summary"]["by_severity"]["high"] == 0
            assert r["files_found"]["SKILL.md"] is True
            assert r["files_found"]["metadata.json"] is True

    def test_missing_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "broken-skill"
            pkg.mkdir()
            (pkg / "metadata.json").write_text(json.dumps(VALID_METADATA), encoding="utf-8")
            r = validate_skill_package(str(pkg))
            assert r["result"] == "FAIL"
            assert r["summary"]["by_severity"]["high"] >= 1

    def test_bad_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "bad-fm"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text("# No frontmatter\n\nJust content.", encoding="utf-8")
            r = validate_skill_package(str(pkg))
            assert r["result"] == "FAIL"

    def test_name_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "real-name"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text("---\nname: wrong-name\ndescription: test\n---\n\n# Wrong\n\n## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n", encoding="utf-8")
            r = validate_skill_package(str(pkg))
            has_mismatch = any(
                "does not match" in i["message"]
                for i in r["validation"]["skill_md"]["frontmatter"]
            )
            assert has_mismatch

    def test_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp, "bad-meta")
            (pkg / "metadata.json").write_text(json.dumps({"name": "bad-meta"}), encoding="utf-8")
            r = validate_skill_package(str(pkg))
            assert r["summary"]["total_issues"] > 0

    def test_generated_by_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp)
            r = validate_skill_package(str(pkg), generated_by="create-skill")
            has_gb_issue = any(
                "generated_by" in i.get("field", "")
                for i in r["validation"]["metadata"]["issues"]
            )
            assert has_gb_issue

    def test_trailing_hyphen_rejected(self):
        """Names ending with a hyphen should be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "bad-name-"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text("---\nname: bad-name-\ndescription: test\n---\n\n## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n", encoding="utf-8")
            (pkg / "metadata.json").write_text(json.dumps(VALID_METADATA), encoding="utf-8")
            r = validate_skill_package(str(pkg))
            fm_issues = r["validation"]["skill_md"]["frontmatter"]
            assert any("must be lowercase" in i["message"] or "alphanumeric" in i["message"] for i in fm_issues), f"Expected name rejection, got: {fm_issues}"

    def test_frontmatter_with_dashes_in_value(self):
        """Frontmatter parser should not be confused by --- in YAML values."""
        content = "---\nname: test-skill\ndescription: A---great library\n---\n\n## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n"
        issues = mod.validate_frontmatter(content, "test-skill")
        # Should parse successfully — no high-severity issues
        high_issues = [i for i in issues if i["severity"] == "high"]
        assert len(high_issues) == 0

    def test_missing_description_section_flagged(self):
        """SKILL.md without a Description section should log a medium body issue."""
        content_no_desc = (
            "---\nname: no-desc\ndescription: a skill missing its Description section\n---\n\n"
            "## Overview\n\nTest\n\n## Key Exports\n\nNone\n\n## Usage\n\nNone\n"
        )
        body_issues = mod.validate_body_structure(content_no_desc)
        desc_issues = [i for i in body_issues if "Description" in i.get("field", "")]
        assert len(desc_issues) == 1
        assert desc_issues[0]["severity"] == "medium"

    def test_skip_frontmatter_omits_frontmatter_pass(self):
        """--skip-frontmatter / skip_frontmatter=True must skip the frontmatter validator entirely."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "skip-fm"
            pkg.mkdir()
            # Deliberately broken frontmatter — would normally produce a high-severity issue
            (pkg / "SKILL.md").write_text(
                "# No frontmatter at all\n\n## Overview\n\nT\n\n## Description\n\nT\n\n## Key Exports\n\nNone\n\n## Usage\n\nT\n",
                encoding="utf-8",
            )
            (pkg / "context-snippet.md").write_text(VALID_SNIPPET.replace("test-skill", "skip-fm"), encoding="utf-8")
            meta = dict(VALID_METADATA)
            meta["name"] = "skip-fm"
            (pkg / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

            r = validate_skill_package(str(pkg), skip_frontmatter=True)
            fm = r["validation"]["skill_md"]["frontmatter"]
            assert isinstance(fm, dict) and "skipped" in fm, f"Expected skipped marker, got: {fm}"
            # No high-severity issues should be raised when frontmatter is skipped on otherwise-valid body/snippet/metadata
            assert r["summary"]["by_severity"]["high"] == 0
            assert r["result"] == "PASS"

    def test_individual_default_has_no_stack_counts(self):
        """Default skill_type='individual' must run legacy body/metadata checks and emit no stack_counts."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp)
            r = validate_skill_package(str(pkg))
            # Legacy body pass runs (a list of issues, not a skipped marker)
            assert isinstance(r["validation"]["skill_md"]["body"], list)
            # Legacy metadata pass runs (issues list present)
            assert "issues" in r["validation"]["metadata"]
            # No stack-specific section leaks into individual mode
            assert "stack_counts" not in r["validation"]


STACK_SKILL_MD = """---
name: demo-stack
description: A demo stack capstone skill
---

# demo-stack (2 libraries, 1 integration)

Header with project name, library count, integration count, forge tier.
"""

STACK_SNIPPET = "[demo-stack v1.0.0]|root: skills/demo-stack/\n|IMPORTANT: Stack capstone\n|stack: lib-a, lib-b\n"

# metadata.json as create-stack-skill writes it from
# src/skf-create-stack-skill/assets/stack-skill-template.md, for a compose-mode
# stack (no AST pass of its own, so no ast_node_count). make_stack_package
# overlays the counts and name each test passes.
STACK_TEMPLATE_META = {
    "skill_type": "stack",
    "name": "demo-stack",
    "version": "1.0.0",
    "generation_date": "2026-07-13",
    "forge_tier": "Deep",
    "confidence_tier": "T1-low",
    "spec_version": "1.3",
    "source_authority": "community",
    "generated_by": "create-stack-skill",
    "exports": [],
    "library_count": 0,
    "integration_count": 0,
    "libraries": ["lib-a", "lib-b"],
    "integration_pairs": [["lib-a", "lib-b"]],
    "language": "typescript",
    "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
    "tool_versions": {"ast_grep": None, "qmd": None, "skf": "3.0.0"},
    "stats": {
        "exports_documented": 0,
        "exports_public_api": 0,
        "exports_internal": 0,
        "exports_total": 0,
        "public_api_coverage": 0.0,
        "total_coverage": 0.0,
        "scripts_count": 0,
        "assets_count": 0,
    },
    "dependencies": [],
    "compatibility": ">=1.0.0",
}


def make_stack_package(tmpdir, *, library_count, ref_libs, catalog, pair_files,
                       integration_count, confidence_distribution, name="demo-stack",
                       meta_overrides=None):
    """Build a stack skill package fixture on disk.

    ref_libs: list of per-library reference basenames (without .md).
    catalog: if True, also write references/stack-catalog.md (must NOT be counted).
    pair_files: list of integration pair basenames (without .md).
    meta_overrides: fields to set on top of STACK_TEMPLATE_META and the counts.
    """
    pkg = Path(tmpdir) / name
    (pkg / "references" / "integrations").mkdir(parents=True)
    (pkg / "SKILL.md").write_text(STACK_SKILL_MD.replace("demo-stack", name), encoding="utf-8")
    (pkg / "context-snippet.md").write_text(STACK_SNIPPET.replace("demo-stack", name), encoding="utf-8")
    for lib in ref_libs:
        (pkg / "references" / f"{lib}.md").write_text(f"# {lib}\n", encoding="utf-8")
    if catalog:
        (pkg / "references" / "stack-catalog.md").write_text("# Catalog\n", encoding="utf-8")
    for pair in pair_files:
        (pkg / "references" / "integrations" / f"{pair}.md").write_text(f"# {pair}\n", encoding="utf-8")
    meta = copy.deepcopy(STACK_TEMPLATE_META)
    meta.update({
        "name": name,
        "library_count": library_count,
        "integration_count": integration_count,
        "confidence_distribution": confidence_distribution,
    })
    meta.update(meta_overrides or {})
    (pkg / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return pkg


class TestSkfValidateOutputStack:
    """Tests for --skill-type stack (stack count-equality validation)."""

    def test_library_count_mismatch_excludes_catalog(self):
        """library_count=3 with 2 real ref files (+ stack-catalog.md) -> exactly one library_count issue."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_stack_package(
                tmp,
                library_count=3,
                ref_libs=["lib-a", "lib-b"],
                catalog=True,
                pair_files=["lib-a-lib-b"],
                integration_count=1,
                confidence_distribution={"t1": 1, "t1_low": 1, "t2": 1, "t3": 0},
            )
            r = validate_skill_package(str(pkg), skill_type="stack")
            sc = r["validation"]["stack_counts"]
            # stack-catalog.md is NOT counted as a per-library file
            assert sc["observed"]["ref_file_count"] == 2
            # integration pair counted separately
            assert sc["observed"]["pair_file_count"] == 1
            # Exactly one issue, and it is the library_count mismatch (3 vs 2)
            assert len(sc["issues"]) == 1
            assert sc["issues"][0]["field"] == "library_count"
            assert sc["observed"]["library_count_meta"] == 3
            # confidence sum matches library_count (both 3) -> no confidence issue
            assert sc["observed"]["confidence_sum"] == 3
            # No individual-skill body issues (body pass is skipped for stack)
            body = r["validation"]["skill_md"]["body"]
            assert isinstance(body, dict) and "skipped" in body
            # Individual metadata schema not applied
            assert "skipped" in r["validation"]["metadata"]

    def test_all_counts_consistent_no_issues(self):
        """Consistent stack package -> zero stack_counts issues."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_stack_package(
                tmp,
                library_count=2,
                ref_libs=["lib-a", "lib-b"],
                catalog=False,
                pair_files=["lib-a-lib-b"],
                integration_count=1,
                confidence_distribution={"t1": 2, "t1_low": 0, "t2": 0, "t3": 0},
            )
            r = validate_skill_package(str(pkg), skill_type="stack")
            sc = r["validation"]["stack_counts"]
            assert sc["issues"] == []
            assert sc["observed"]["ref_file_count"] == 2
            assert sc["observed"]["pair_file_count"] == 1
            assert sc["observed"]["confidence_sum"] == 2

    def test_integration_and_confidence_mismatch(self):
        """integration_count and confidence-sum mismatches each surface an issue."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_stack_package(
                tmp,
                library_count=2,
                ref_libs=["lib-a", "lib-b"],
                catalog=True,
                pair_files=["lib-a-lib-b"],
                integration_count=2,  # only 1 pair file exists -> mismatch
                confidence_distribution={"t1": 1, "t1_low": 0, "t2": 0, "t3": 0},  # sums to 1, not 2
            )
            r = validate_skill_package(str(pkg), skill_type="stack")
            sc = r["validation"]["stack_counts"]
            fields = {i["field"] for i in sc["issues"]}
            assert "integration_count" in fields
            assert "confidence_distribution" in fields
            assert "library_count" not in fields  # 2 == 2

    def test_stack_missing_metadata(self):
        """Missing metadata.json -> stack_counts skipped, not a crash."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo-stack"
            (pkg / "references").mkdir(parents=True)
            (pkg / "SKILL.md").write_text(STACK_SKILL_MD, encoding="utf-8")
            r = validate_skill_package(str(pkg), skill_type="stack")
            assert "skipped" in r["validation"]["stack_counts"]

    def test_validate_stack_counts_missing_fields(self):
        """Absent library_count / integration_count / confidence_distribution each flag."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo-stack"
            (pkg / "references").mkdir(parents=True)
            issues, observed = validate_stack_counts(str(pkg), {})
            fields = {i["field"] for i in issues}
            assert fields == {"library_count", "integration_count", "confidence_distribution"}
            assert observed["confidence_sum"] is None


# --- Stack structure pass (--skill-type stack) ------------------------------

# A stack package as create-stack-skill writes it from the stack template, with
# two libraries and one integration pair. `catalog` puts the Library Reference
# Index and the Per-Library Summaries inline in SKILL.md or behind the Library
# Catalog pointer in references/stack-catalog.md.
FULL_STACK_HEADER = """---
name: demo-stack
description: A demo stack capstone skill
---

# demo Stack Skill

> 2 libraries | 1 integration patterns | Forge tier: Deep

## Integration Patterns

### Cross-Cutting Patterns

None across three libraries.

### Library Pair Integrations

#### lib-a + lib-b
**Type:** Middleware Chain
**Pattern:** `a()` feeds `b()`.
**Key files:** src/app.ts
**Confidence:** T1-low (grep-co-import)

"""

FULL_STACK_INDEX = """## Library Reference Index

| Library | Imports | Key Exports | Confidence | Reference |
|---------|---------|-------------|------------|-----------|
| lib-a | 3 | `a()` | T1 | [ref]({prefix}lib-a.md) |
| lib-b | 2 | `b()` | T1-low | [ref]({prefix}lib-b.md) |

## Per-Library Summaries

### lib-a
**Role in stack:** the entry point
**Key exports used:** `a()`
**Usage pattern:** called once at start-up
**Confidence:** T1

### lib-b
**Role in stack:** the sink
**Key exports used:** `b()`
**Usage pattern:** receives what `a()` returns
**Confidence:** T1-low

"""

FULL_STACK_POINTER = """## Library Catalog

2 libraries indexed in [references/stack-catalog.md](references/stack-catalog.md): reference-index table and
per-library summaries.

"""

FULL_STACK_CONVENTIONS = """## Conventions

- Call `a()` before `b()`.
"""

LIBRARY_REFERENCE = """# {name} Reference

**Version:** 1.0.0
**Import count:** 3 files
**Confidence:** {tier}

## Key Exports

`{name}()`

## Usage Patterns

Called at start-up.

## Common Imports

`import {name}`
"""

PAIR_REFERENCE = """# lib-a + lib-b Integration

**Type:** Middleware Chain
**Co-import files:** 2
**Confidence:** T1-low (grep-co-import)

## Integration Pattern

`a()` feeds `b()`.

## Key Files

src/app.ts:12

## Usage Convention

Call them in order.
"""


def make_full_stack(tmpdir, *, catalog="inline", skill_md=None, meta_overrides=None, drop_keys=()):
    """A template-conformant stack package; `skill_md` replaces the SKILL.md text."""
    pkg = Path(tmpdir) / "demo-stack"
    (pkg / "references" / "integrations").mkdir(parents=True)
    if skill_md is None:
        if catalog == "inline":
            skill_md = FULL_STACK_HEADER + FULL_STACK_INDEX.replace("{prefix}", "references/") + FULL_STACK_CONVENTIONS
        else:
            skill_md = FULL_STACK_HEADER + FULL_STACK_POINTER + FULL_STACK_CONVENTIONS
            (pkg / "references" / "stack-catalog.md").write_text(
                "# demo Stack: Library Catalog\n\n" + FULL_STACK_INDEX.replace("{prefix}", ""), encoding="utf-8")
    (pkg / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (pkg / "context-snippet.md").write_text(STACK_SNIPPET, encoding="utf-8")
    for name, tier in (("lib-a", "T1"), ("lib-b", "T1-low")):
        (pkg / "references" / f"{name}.md").write_text(
            LIBRARY_REFERENCE.replace("{name}", name).replace("{tier}", tier), encoding="utf-8")
    (pkg / "references" / "integrations" / "lib-a-lib-b.md").write_text(PAIR_REFERENCE, encoding="utf-8")
    meta = copy.deepcopy(STACK_TEMPLATE_META)
    meta.update({
        "library_count": 2,
        "integration_count": 1,
        "confidence_distribution": {"t1": 1, "t1_low": 1, "t2": 0, "t3": 0},
    })
    meta.update(meta_overrides or {})
    for key in drop_keys:
        del meta[key]
    (pkg / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return pkg


def structure(pkg, **kwargs):
    result = validate_skill_package(str(pkg), generated_by="create-stack-skill", skill_type="stack", **kwargs)
    return result["validation"]["stack_structure"]


def issues_by(section, check):
    return [issue for issue in section["issues"] if issue["check"] == check]


class TestStackStructure:
    """--skill-type stack: validation.stack_structure, the checks of validate.md §4 to §7 (#606)."""

    @pytest.mark.parametrize("catalog", ["inline", "pointer"])
    def test_a_template_stack_has_no_issue(self, catalog):
        with tempfile.TemporaryDirectory() as tmp:
            section = structure(make_full_stack(tmp, catalog=catalog))
            assert section["issues"] == []
            observed = section["observed"]
            assert observed["catalog"] == catalog
            assert observed["dominant_tier"] == "T1-low"
            assert observed["tier_rule"] == "skf-render-stack-metadata.py"
            assert (observed["reference_files"], observed["pair_files"]) == (2, 1)
            # two summaries, one pair entry, two reference files and one pair file
            assert observed["tier_labels_checked"] == 6
            assert observed["links_checked"] == (2 if catalog == "inline" else 3)

    def test_the_pass_runs_only_for_a_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = validate_skill_package(str(make_full_stack(tmp)))
            assert "stack_structure" not in r["validation"]

    def test_issues_count_in_the_summary_without_failing_the_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, meta_overrides={"source_authority": "vendor"})
            r = validate_skill_package(str(pkg), skill_type="stack")
            assert [i["field"] for i in r["validation"]["stack_structure"]["issues"]] == ["source_authority"]
            assert r["summary"]["by_severity"]["medium"] == 1
            assert r["result"] == "PASS"

    # -- §4: SKILL.md headings, catalog and links --------------------------------

    def test_a_catalog_link_into_references_references_is_flagged(self):
        """#535: a catalog moved into references/ keeps no references/ prefix."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, catalog="pointer")
            catalog = pkg / "references" / "stack-catalog.md"
            catalog.write_text(catalog.read_text(encoding="utf-8").replace("](lib-a.md)", "](references/lib-a.md)"),
                               encoding="utf-8")
            issues = issues_by(structure(pkg), "skill_md")
            assert [(i["field"], i["severity"]) for i in issues] == [("link", "medium")]
            assert "stack-catalog.md links `references/lib-a.md`" in issues[0]["message"]

    def test_a_broken_link_in_skill_md_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            (pkg / "references" / "lib-b.md").unlink()
            section = structure(pkg)
            links = [i for i in issues_by(section, "skill_md") if i["field"] == "link"]
            assert len(links) == 1 and "`references/lib-b.md`" in links[0]["message"]

    def test_links_that_are_no_files_are_not_checked(self):
        extra = ("See [the spec](https://example.com/spec), [below](#conventions), [mail](mailto:a@b.c) and "
                 "[the part](references/lib-a.md#key-exports).\n\n"
                 "`[ref](references/missing.md)` is how a link reads.\n\n"
                 "```md\n[ref](references/missing.md)\n```\n")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, skill_md=FULL_STACK_HEADER + FULL_STACK_INDEX.replace("{prefix}", "references/")
                                  + FULL_STACK_CONVENTIONS + "\n" + extra)
            section = structure(pkg)
            assert section["issues"] == []
            assert section["observed"]["links_checked"] == 3

    def test_a_link_no_file_system_can_hold_is_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, skill_md=FULL_STACK_HEADER + FULL_STACK_INDEX.replace("{prefix}", "references/")
                                  + FULL_STACK_CONVENTIONS + "\nSee [the notes](notes%00.md).\n")
            links = [i for i in issues_by(structure(pkg), "skill_md") if i["field"] == "link"]
            assert len(links) == 1 and "notes" in links[0]["message"]

    def test_a_pointer_without_its_catalog_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, catalog="pointer")
            (pkg / "references" / "stack-catalog.md").unlink()
            fields = [(i["field"], i["message"]) for i in issues_by(structure(pkg), "skill_md")]
            assert ("catalog", "the `## Library Catalog` pointer's `references/stack-catalog.md` does not exist") in fields
            assert any(field == "link" for field, _ in fields)

    def test_a_catalog_without_its_sections_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, catalog="pointer")
            (pkg / "references" / "stack-catalog.md").write_text("# Catalog\n\n## Library Reference Index\n",
                                                                  encoding="utf-8")
            messages = [i["message"] for i in issues_by(structure(pkg), "skill_md")]
            assert messages == ["`references/stack-catalog.md` has no `## Per-Library Summaries` section"]

    def test_a_pointer_that_links_elsewhere_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, catalog="pointer")
            text = (pkg / "SKILL.md").read_text(encoding="utf-8")
            (pkg / "SKILL.md").write_text(text.replace("](references/stack-catalog.md)", "](references/lib-a.md)"),
                                          encoding="utf-8")
            messages = [i["message"] for i in issues_by(structure(pkg), "skill_md")]
            assert messages == ["the `## Library Catalog` pointer does not link `references/stack-catalog.md`"]

    def test_neither_catalog_form_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            index_only = FULL_STACK_INDEX.replace("{prefix}", "references/").split("## Per-Library Summaries")[0]
            pkg = make_full_stack(tmp, skill_md=FULL_STACK_HEADER + index_only + FULL_STACK_CONVENTIONS)
            section = structure(pkg)
            catalog = [i["message"] for i in issues_by(section, "skill_md") if i["field"] == "catalog"]
            assert len(catalog) == 1
            assert "no `## Per-Library Summaries`" in catalog[0] and "`## Library Catalog`" in catalog[0]
            assert section["observed"]["catalog"] is None

    def test_missing_and_misplaced_sections_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = FULL_STACK_INDEX.replace("{prefix}", "references/")
            head, patterns = FULL_STACK_HEADER.split("## Integration Patterns")
            pkg = make_full_stack(tmp, skill_md=head + index + "## Integration Patterns" + patterns)
            messages = [i["message"] for i in issues_by(structure(pkg), "skill_md")]
            assert "SKILL.md has no `## Conventions` section" in messages
            assert "`## Integration Patterns` comes after the per-library summaries" in messages

    def test_a_stack_with_no_integration_needs_no_integration_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = FULL_STACK_HEADER.split("## Integration Patterns")[0].replace("1 integration patterns",
                                                                                  "0 integration patterns")
            pkg = make_full_stack(tmp, skill_md=head + FULL_STACK_INDEX.replace("{prefix}", "references/")
                                  + FULL_STACK_CONVENTIONS,
                                  meta_overrides={"integration_count": 0, "integration_pairs": []})
            (pkg / "references" / "integrations" / "lib-a-lib-b.md").unlink()
            assert structure(pkg)["issues"] == []

    def test_pairs_without_their_section_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = FULL_STACK_HEADER.split("### Library Pair Integrations")[0]
            pkg = make_full_stack(tmp, skill_md=head + FULL_STACK_INDEX.replace("{prefix}", "references/")
                                  + FULL_STACK_CONVENTIONS)
            messages = [i["message"] for i in issues_by(structure(pkg), "skill_md")]
            assert messages == ["`## Integration Patterns` has no `### Library Pair Integrations` section"]

    @pytest.mark.parametrize("line, expected", [
        (None, "SKILL.md has no `> {lib_count} libraries"),
        ("> 3 libraries | 1 integration patterns | Forge tier: Deep", "gives 3 for library_count"),
        ("> 2 libraries | 4 integration patterns | Forge tier: Deep", "gives 4 for integration_count"),
        ("> 2 libraries | 1 integration patterns | Forge tier: Forge+", "gives forge tier Forge+"),
    ], ids=["missing", "library-count", "integration-count", "forge-tier"])
    def test_the_header_line_agrees_with_metadata(self, line, expected):
        header_line = "> 2 libraries | 1 integration patterns | Forge tier: Deep"
        with tempfile.TemporaryDirectory() as tmp:
            skill_md = (FULL_STACK_HEADER.replace(header_line, line or "The demo stack.")
                        + FULL_STACK_INDEX.replace("{prefix}", "references/") + FULL_STACK_CONVENTIONS)
            messages = [i["message"] for i in issues_by(structure(make_full_stack(tmp, skill_md=skill_md)), "skill_md")]
            assert len(messages) == 1 and expected in messages[0], messages

    def test_a_missing_title_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_md = (FULL_STACK_HEADER.replace("# demo Stack Skill\n", "")
                        + FULL_STACK_INDEX.replace("{prefix}", "references/") + FULL_STACK_CONVENTIONS)
            messages = [i["message"] for i in issues_by(structure(make_full_stack(tmp, skill_md=skill_md)), "skill_md")]
            assert messages == ["SKILL.md has no title (`# {project_name} Stack Skill`)"]

    def test_headings_inside_fenced_code_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_md = (FULL_STACK_HEADER + FULL_STACK_INDEX.replace("{prefix}", "references/")
                        + "```markdown\n## Conventions\n```\n")
            messages = [i["message"] for i in issues_by(structure(make_full_stack(tmp, skill_md=skill_md)), "skill_md")]
            assert messages == ["SKILL.md has no `## Conventions` section"]

    # -- §5: metadata.json ------------------------------------------------------

    @pytest.mark.parametrize("overrides, field, needle", [
        ({"skill_type": "single"}, "skill_type", "not 'stack'"),
        ({"name": "other-stack"}, "name", "does not match the package folder 'demo-stack'"),
        ({"version": ""}, "version", "non-empty string"),
        ({"generation_date": 20260930}, "generation_date", "non-empty string"),
        ({"forge_tier": "Ultra"}, "forge_tier", "not in ['Quick', 'Forge', 'Forge+', 'Deep']"),
        ({"confidence_tier": "Deep"}, "confidence_tier", "not in ['T1', 'T1-low', 'T2', 'T3']"),
        ({"confidence_tier": "T1"}, "confidence_tier", "is not the dominant tier of confidence_distribution ('T1-low')"),
        ({"source_authority": "vendor"}, "source_authority", "not in ['official', 'community', 'internal']"),
        ({"exports": {}}, "exports", "must be an array"),
        ({"libraries": []}, "libraries", "non-empty array"),
        ({"libraries": ["lib-a", "lib-a"]}, "libraries", "names a library twice"),
        ({"libraries": ["lib-a"]}, "libraries", "lists 1 libraries; library_count is 2"),
        ({"integration_pairs": [["lib-a", "lib-z"]]}, "integration_pairs", "names a library libraries does not list"),
        ({"integration_pairs": [["lib-a", "lib-a"]]}, "integration_pairs", "two different library names"),
        ({"integration_pairs": [["lib-a", "lib-b"], ["lib-b", "lib-a"]]}, "integration_pairs", "twice"),
        ({"integration_pairs": "lib-a+lib-b"}, "integration_pairs", "must be an array"),
        ({"confidence_distribution": {"t1": 1, "t1_low": 1, "t2": 0}}, "confidence_distribution",
         "confidence_distribution.t3 must be a whole number"),
    ], ids=["skill-type", "name", "version", "generation-date", "forge-tier", "confidence-tier-enum",
            "confidence-tier-dominant", "source-authority", "exports", "libraries-empty", "libraries-twice",
            "libraries-count", "pair-unknown-library", "pair-self", "pair-twice", "pairs-not-a-list",
            "distribution-bin-missing"])
    def test_a_metadata_value_off_the_template_is_flagged(self, overrides, field, needle):
        with tempfile.TemporaryDirectory() as tmp:
            issues = issues_by(structure(make_full_stack(tmp, meta_overrides=overrides)), "metadata")
            hits = [i for i in issues if i["field"] == field and needle in i["message"]]
            assert hits, issues
            assert all(i["severity"] == "medium" for i in hits)

    @pytest.mark.parametrize("key", mod._STACK_REQUIRED_KEYS)
    def test_a_missing_template_key_is_flagged(self, key):
        with tempfile.TemporaryDirectory() as tmp:
            issues = issues_by(structure(make_full_stack(tmp, drop_keys=(key,))), "metadata")
            assert [i["field"] for i in issues] == [key]

    def test_the_required_keys_are_the_template_keys(self):
        """Every key the stack template writes, less ast_node_count and the keys the count pass checks."""
        keys = template_metadata_keys("src/skf-create-stack-skill/assets/stack-skill-template.md")
        assert set(mod._STACK_REQUIRED_KEYS) == keys - {
            "ast_node_count", "library_count", "integration_count", "confidence_distribution"}

    def test_the_dominant_tier_is_recomputed_with_the_stack_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = {"t1": 0, "t1_low": 1, "t2": 1, "t3": 0}  # a tie goes to the weaker tier
            pkg = make_full_stack(tmp, meta_overrides={"confidence_distribution": dist, "confidence_tier": "T2"})
            section = structure(pkg)
            assert section["issues"] == []
            assert section["observed"]["dominant_tier"] == "T2"

    def test_a_missing_tier_rule_is_a_low_note(self, monkeypatch):
        monkeypatch.setattr(mod, "_stack_rules", lambda: None)
        with tempfile.TemporaryDirectory() as tmp:
            section = structure(make_full_stack(tmp, meta_overrides={"confidence_tier": "T1"}))
            assert [(i["severity"], i["field"]) for i in section["issues"]] == [("low", "confidence_tier")]
            assert "re-install SKF" in section["issues"][0]["message"]
            assert section["observed"]["dominant_tier"] is None

    def test_the_rule_is_loaded_from_beside_the_validator(self):
        rules = mod._stack_rules()
        assert rules is not None
        assert rules.dominant_tier({"t1": 2, "t1_low": 2, "t2": 0, "t3": 0}) == "T1-low"

    def test_forge_tier_is_checked_against_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            assert issues_by(structure(pkg, forge_tier="Deep"), "metadata") == []
            issues = issues_by(structure(pkg, forge_tier="Forge"), "metadata")
            assert [i["message"] for i in issues] == ["forge_tier 'Deep' is not this run's forge tier 'Forge'"]

    def test_the_cli_passes_the_run_forge_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)

            def run(tier):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), str(pkg), "--generated-by", "create-stack-skill",
                     "--skill-type", "stack", "--forge-tier", tier],
                    capture_output=True, text=True,
                )
                assert proc.returncode == 0, proc.stderr
                return json.loads(proc.stdout)["validation"]["stack_structure"]["issues"]

            assert run("Deep") == []
            assert [i["field"] for i in run("Quick")] == ["forge_tier"]

    def test_a_generated_by_mismatch_is_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            issues = structure(make_full_stack(tmp, meta_overrides={"generated_by": "quick-skill"}))["issues"]
            assert [(i["severity"], i["field"]) for i in issues] == [("low", "generated_by")]

    def test_skill_md_and_references_are_checked_without_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, skill_md=FULL_STACK_HEADER + FULL_STACK_INDEX.replace("{prefix}", "references/"))
            (pkg / "metadata.json").unlink()
            section = structure(pkg)
            assert [i["message"] for i in section["issues"]] == ["SKILL.md has no `## Conventions` section"]

    def test_metadata_that_is_no_object_fails_without_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            (pkg / "metadata.json").write_text("[]", encoding="utf-8")
            r = validate_skill_package(str(pkg), skill_type="stack")
            assert r["validation"]["metadata"] == {"error": "metadata.json is not a JSON object"}
            assert "skipped" in r["validation"]["stack_counts"]
            assert r["validation"]["stack_structure"]["issues"] == []
            assert r["result"] == "FAIL"

    # -- §6: reference and pair files ----------------------------------------------

    def test_reference_files_off_the_template_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            (pkg / "references" / "lib-a.md").write_text("# lib-a Reference\n\n**Confidence:** T1\n\n## Key Exports\n",
                                                          encoding="utf-8")
            (pkg / "references" / "integrations" / "lib-a-lib-b.md").write_text(
                "**Type:** Middleware Chain\n**Confidence:** T1-low\n\n## Integration Pattern\n", encoding="utf-8")
            issues = issues_by(structure(pkg), "references")
            assert [(i["field"], i["message"].split(" has ")[1]) for i in issues] == [
                ("references/lib-a.md", "no `**Version:**` line"),
                ("references/lib-a.md", "no `## Usage Patterns` section"),
                ("references/integrations/lib-a-lib-b.md", "no title (`# ...`)"),
                ("references/integrations/lib-a-lib-b.md", "no `## Key Files` section"),
            ]

    def test_the_catalog_is_no_reference_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            section = structure(make_full_stack(tmp, catalog="pointer"))
            assert section["observed"]["reference_files"] == 2
            assert issues_by(section, "references") == []

    def test_a_listed_library_or_pair_without_its_file_is_flagged(self):
        """Misnamed files with the right counts: the count pass agrees, the by-name check does not."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            refs = pkg / "references"
            (refs / "lib-b.md").rename(refs / "lib-c.md")
            (refs / "integrations" / "lib-a-lib-b.md").rename(refs / "integrations" / "lib-a-lib-c.md")
            r = validate_skill_package(str(pkg), generated_by="create-stack-skill", skill_type="stack")
            assert r["validation"]["stack_counts"]["issues"] == []
            issues = issues_by(r["validation"]["stack_structure"], "references")
            assert [(i["field"], i["message"]) for i in issues] == [
                ("references/lib-b.md", "libraries lists 'lib-b', but references/lib-b.md does not exist"),
                ("references/integrations/lib-a-lib-b.md",
                 "integration_pairs lists 'lib-a' + 'lib-b', but references/integrations/lib-a-lib-b.md "
                 "does not exist"),
            ]

    def test_a_pair_file_named_in_either_order_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            pairs = pkg / "references" / "integrations"
            (pairs / "lib-a-lib-b.md").rename(pairs / "lib-b-lib-a.md")
            assert issues_by(structure(pkg), "references") == []

    def test_a_library_name_no_file_system_can_hold_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, meta_overrides={"libraries": ["lib-a", "lib\x00b"]})
            fields = [i["field"] for i in issues_by(structure(pkg), "references")]
            assert fields == ["references/lib\x00b.md"]

    # -- §7: tier labels -------------------------------------------------------------

    def test_a_missing_tier_label_is_flagged_where_it_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            skill_md = (pkg / "SKILL.md").read_text(encoding="utf-8")
            skill_md = skill_md.replace("**Confidence:** T1-low (grep-co-import)", "**Confidence:** {T1/T1-low/T2/T3}")
            skill_md = skill_md.replace("**Usage pattern:** called once at start-up\n**Confidence:** T1\n",
                                        "**Usage pattern:** called once at start-up\n")
            (pkg / "SKILL.md").write_text(skill_md, encoding="utf-8")
            pair = pkg / "references" / "integrations" / "lib-a-lib-b.md"
            pair.write_text(pair.read_text(encoding="utf-8").replace("**Confidence:** T1-low (grep-co-import)\n", "")
                            + "\n**Confidence:** T1-low\n", encoding="utf-8")
            messages = [i["message"] for i in issues_by(structure(pkg), "tier_labels")]
            assert messages == [
                "the per-library summary `### lib-a` in SKILL.md has no `**Confidence:**` T-code label",
                "the pair entry `#### lib-a + lib-b` in SKILL.md has no `**Confidence:**` T-code label",
                "references/integrations/lib-a-lib-b.md has no `**Confidence:**` T-code label in its header",
            ]

    def test_catalog_summaries_carry_the_labels_in_the_pointer_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp, catalog="pointer")
            catalog = pkg / "references" / "stack-catalog.md"
            catalog.write_text(catalog.read_text(encoding="utf-8").replace("**Confidence:** T1-low\n", ""),
                               encoding="utf-8")
            messages = [i["message"] for i in issues_by(structure(pkg), "tier_labels")]
            assert messages == [
                "the per-library summary `### lib-b` in stack-catalog.md has no `**Confidence:**` T-code label"]

    @pytest.mark.parametrize("label", [
        "**Confidence:** T1-low (dominant bin t1_low)",
        "- **Confidence:** T3 [composed]",
        "**Confidence:** T2",
    ], ids=["with-note", "list-item", "bare"])
    def test_a_t_code_label_passes(self, label):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            ref = pkg / "references" / "lib-b.md"
            ref.write_text(ref.read_text(encoding="utf-8").replace("**Confidence:** T1-low", label), encoding="utf-8")
            assert issues_by(structure(pkg), "tier_labels") == []

    @pytest.mark.parametrize("label", ["**Confidence:** Deep", "**Confidence:** T1-lowish", "Confidence: T1"],
                             ids=["forge-tier", "not-a-t-code", "not-bold"])
    def test_a_label_that_is_no_t_code_is_flagged(self, label):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_full_stack(tmp)
            ref = pkg / "references" / "lib-b.md"
            ref.write_text(ref.read_text(encoding="utf-8").replace("**Confidence:** T1-low", label), encoding="utf-8")
            assert [i["field"] for i in issues_by(structure(pkg), "tier_labels")] == ["tier_label"]


# --- Export-gate mode ------------------------------------------------------

# A complete single skill compiled at Forge+: every required field, and every
# recommended one (ast_node_count too, since it counts T1 signatures).
EXPORT_GATE_META = {
    "name": "demo",
    "version": "1.0.0",
    "skill_type": "single",
    "source_authority": "community",
    "exports": ["foo", "bar"],
    "generation_date": "2026-07-13",
    "confidence_tier": "Forge+",
    "description": "A demo skill for export-gate validation",
    "source_repo": "https://github.com/test/demo",
    "language": "typescript",
    "ast_node_count": 34,
    "confidence_distribution": {"t1": 2, "t1_low": 0, "t2": 0, "t3": 0},
    "tool_versions": {"ast_grep": "0.45.3", "qmd": None, "skf": "3.0.0"},
}

# A complete Quick single skill as quick-skill writes it: no AST pass, so no
# ast_node_count and no T1 signatures.
QUICK_EXPORT_GATE_META = {
    "name": "demo",
    "version": "1.0.0",
    "description": "A demo skill for export-gate validation",
    "skill_type": "single",
    "source_authority": "community",
    "source_repo": "https://github.com/test/demo",
    "language": "typescript",
    "generated_by": "quick-skill",
    "generation_date": "2026-07-13",
    "confidence_tier": "Quick",
    "exports": ["foo", "bar"],
    "confidence_distribution": {"t1": 0, "t1_low": 2, "t2": 0, "t3": 0},
    "tool_versions": {"ast_grep": None, "qmd": None, "skf": "3.0.0"},
}

REPO_ROOT = Path(__file__).parent.parent


def template_metadata_keys(relpath):
    """Top-level keys of the metadata.json block in a generator template."""
    text = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    block = re.search(r"##[^\n]*metadata\.json[^\n]*\n+```json\n(.*?)\n```", text, re.DOTALL)
    assert block, f"no metadata.json block in {relpath}"
    return set(re.findall(r'^  "([a-z_]+)":', block.group(1), re.MULTILINE))

EXPORT_GATE_SKILL_MD = """---
name: demo
description: A demo skill for export-gate validation
---

# demo

## Overview

Demo skill.
"""


def make_export_gate_package(tmpdir, *, meta=None, skill_md=None, name="demo"):
    """Build a minimal export-gate skill package fixture (SKILL.md + metadata.json)."""
    pkg = Path(tmpdir) / name
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(
        skill_md if skill_md is not None else EXPORT_GATE_SKILL_MD, encoding="utf-8"
    )
    m = copy.deepcopy(EXPORT_GATE_META) if meta is None else meta
    (pkg / "metadata.json").write_text(json.dumps(m), encoding="utf-8")
    return pkg


class TestSkfValidateOutputExportGate:
    """Tests for --export-gate (skf-export-skill publishing gate)."""

    def test_fully_valid_package_ready(self):
        """A complete, valid package -> export_status=READY, zero high, PASS."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp)
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["mode"] == "export-gate"
            assert r["export_status"] == "READY"
            assert r["summary"]["by_severity"]["high"] == 0
            assert r["result"] == "PASS"
            # No enum, recommended-field or crossref issues on a clean package.
            assert r["validation"]["metadata"]["enum_issues"] == []
            assert r["validation"]["metadata"]["recommended_missing"] == []
            assert r["validation"]["crossref_7b"]["missing"] == []
            assert r["validation"]["crossref_7b"]["orphans"] == []

    def test_bad_skill_type_enum_not_ready(self):
        """skill_type='bogus' -> high enum issue naming skill_type, NOT_READY."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = dict(EXPORT_GATE_META)
            meta["skill_type"] = "bogus"
            pkg = make_export_gate_package(tmp, meta=meta)
            r = validate_skill_package(str(pkg), export_gate=True)
            enum_fields = {i["field"] for i in r["validation"]["metadata"]["enum_issues"]}
            assert "skill_type" in enum_fields
            assert all(i["severity"] == "high" for i in r["validation"]["metadata"]["enum_issues"])
            assert r["export_status"] == "NOT_READY"
            assert r["result"] == "FAIL"

    def test_missing_exports_required_field(self):
        """metadata missing `exports` -> high required-field issue for exports."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = dict(EXPORT_GATE_META)
            del meta["exports"]
            pkg = make_export_gate_package(tmp, meta=meta)
            r = validate_skill_package(str(pkg), export_gate=True)
            issues = r["validation"]["metadata"]["issues"]
            exports_issues = [i for i in issues if i["field"] == "exports"]
            assert len(exports_issues) == 1
            assert exports_issues[0]["severity"] == "high"
            assert r["export_status"] == "NOT_READY"

    def test_empty_exports_is_low_warning(self):
        """Empty exports array is a low warning (graceful), not a hard halt."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = dict(EXPORT_GATE_META)
            meta["exports"] = []
            pkg = make_export_gate_package(tmp, meta=meta)
            r = validate_skill_package(str(pkg), export_gate=True)
            issues = r["validation"]["metadata"]["issues"]
            exports_issues = [i for i in issues if i["field"] == "exports"]
            assert len(exports_issues) == 1
            assert exports_issues[0]["severity"] == "low"
            # Low-only -> WARNINGS, still PASS (does not block export).
            assert r["summary"]["by_severity"]["high"] == 0
            assert r["export_status"] == "WARNINGS"
            assert r["result"] == "PASS"

    def test_section_7b_crossref_missing_and_orphan(self):
        """§7b names scripts/run.py but only scripts/other.py exists on disk."""
        skill_md = (
            "---\nname: demo\ndescription: A demo skill with a scripts manifest\n---\n\n"
            "# demo\n\n## Overview\n\nDemo.\n\n"
            "## Scripts & Assets\n\n"
            "| File | Purpose | Provenance |\n"
            "|------|---------|------------|\n"
            "| `scripts/run.py` | runs the thing | [SRC:src/run.py:L1] |\n\n"
            "Load scripts from `scripts/` when directed by the instructions above.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, skill_md=skill_md)
            (pkg / "scripts").mkdir()
            (pkg / "scripts" / "other.py").write_text("# other\n", encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            cr = r["validation"]["crossref_7b"]
            assert "scripts/run.py" in cr["missing"]
            assert "scripts/other.py" in cr["orphans"]
            # Missing file -> high; orphan -> low.
            missing_issue = [i for i in cr["issues"] if "scripts/run.py" in i["message"]]
            orphan_issue = [i for i in cr["issues"] if "scripts/other.py" in i["message"]]
            assert missing_issue and missing_issue[0]["severity"] == "high"
            assert orphan_issue and orphan_issue[0]["severity"] == "low"
            assert r["export_status"] == "NOT_READY"

    def test_section_7b_all_referenced_no_issues(self):
        """§7b names exactly the file on disk -> no missing, no orphan."""
        skill_md = (
            "---\nname: demo\ndescription: A demo skill with a scripts manifest\n---\n\n"
            "# demo\n\n## Overview\n\nDemo.\n\n"
            "## Scripts & Assets\n\n"
            "| `scripts/run.py` | runs the thing | [SRC:src/run.py:L1] |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, skill_md=skill_md)
            (pkg / "scripts").mkdir()
            (pkg / "scripts" / "run.py").write_text("# run\n", encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            cr = r["validation"]["crossref_7b"]
            assert cr["missing"] == []
            assert cr["orphans"] == []
            assert r["export_status"] == "READY"

    def test_missing_metadata_json_not_ready(self):
        """metadata.json absent -> high issue, NOT_READY, no crash."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text(EXPORT_GATE_SKILL_MD, encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["files_found"]["metadata.json"] is False
            assert r["export_status"] == "NOT_READY"
            assert any(i["field"] == "metadata.json" for i in r["validation"]["metadata"]["issues"])

    def test_invalid_json_not_ready(self):
        """Malformed metadata.json -> high JSON parse issue, NOT_READY."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text(EXPORT_GATE_SKILL_MD, encoding="utf-8")
            (pkg / "metadata.json").write_text("{not valid json", encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["export_status"] == "NOT_READY"
            assert any("parse error" in i["message"] for i in r["validation"]["metadata"]["issues"])

    @pytest.mark.parametrize("text", ["[]", '"demo"', "null"])
    def test_metadata_not_an_object_not_ready(self, text):
        """metadata.json that parses to a non-object -> high issue, NOT_READY, no crash."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text(EXPORT_GATE_SKILL_MD, encoding="utf-8")
            (pkg / "metadata.json").write_text(text, encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            meta = r["validation"]["metadata"]
            assert meta["issues"] == [
                {"severity": "high", "field": "metadata.json", "message": "metadata.json is not a JSON object"}
            ]
            assert meta["enum_issues"] == []
            assert meta["recommended_missing"] == []
            assert r["export_status"] == "NOT_READY"
            assert r["result"] == "FAIL"

    def test_empty_skill_md_flagged(self):
        """Empty SKILL.md -> high presence issue."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, skill_md="   \n")
            r = validate_skill_package(str(pkg), export_gate=True)
            assert any(i["field"] == "SKILL.md" for i in r["validation"]["skill_md"]["issues"])
            assert r["export_status"] == "NOT_READY"

    def test_crossref_deterministic_sorted(self):
        """crossref_section_7b returns sorted, deterministic lists."""
        skill_md = (
            "# demo\n\n## Scripts & Assets\n\n"
            "`scripts/a.py` `scripts/b.py` `assets/z.json`\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "scripts").mkdir(parents=True)
            (pkg / "assets").mkdir(parents=True)
            (pkg / "scripts" / "m.py").write_text("x", encoding="utf-8")
            (pkg / "scripts" / "c.py").write_text("x", encoding="utf-8")
            missing, orphans = crossref_section_7b(skill_md, str(pkg))
            # missing = referenced - on_disk, sorted
            assert missing == sorted(missing)
            assert missing == ["assets/z.json", "scripts/a.py", "scripts/b.py"]
            # orphans = on_disk - referenced, sorted
            assert orphans == ["scripts/c.py", "scripts/m.py"]

    def test_no_section_7b_no_refs(self):
        """Absent Section 7b -> empty referenced set (on-disk files are orphans)."""
        skill_md = "# demo\n\n## Overview\n\nNo scripts section here.\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "scripts").mkdir(parents=True)
            (pkg / "scripts" / "loose.py").write_text("x", encoding="utf-8")
            missing, orphans = crossref_section_7b(skill_md, str(pkg))
            assert missing == []
            assert orphans == ["scripts/loose.py"]

    def test_metadata_export_gate_direct_all_enums(self):
        """validate_metadata_export_gate flags all three enum mismatches."""
        meta = {
            "name": "x",
            "version": "1.0.0",
            "skill_type": "nope",
            "source_authority": "nope",
            "confidence_tier": "nope",
            "exports": ["a"],
            "generation_date": "2026-07-13",
        }
        required_issues, enum_issues, recommended_missing = validate_metadata_export_gate(meta)
        assert required_issues == []
        enum_fields = {i["field"] for i in enum_issues}
        assert enum_fields == {"skill_type", "source_authority", "confidence_tier"}
        assert all(i["severity"] == "high" for i in enum_issues)
        # No recommended set applies to an unknown skill_type.
        assert recommended_missing == []

    def test_export_gate_does_not_alter_default_path(self):
        """Regression guard: default (export_gate=False) output has no export-gate keys."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_valid_package(tmp)
            r = validate_skill_package(str(pkg))
            # None of the export-gate-only keys leak into the legacy output.
            assert "export_status" not in r
            assert "mode" not in r
            assert "crossref_7b" not in r["validation"]
            # Legacy individual-mode output shape is intact.
            assert r["result"] == "PASS"
            assert "issues" in r["validation"]["metadata"]
            assert isinstance(r["validation"]["skill_md"]["body"], list)

    def test_section_7b_upstream_path_not_a_bundled_file(self):
        """An upstream path whose tail is scripts/… is not read as a bundled file."""
        skill_md = (
            "# demo\n\n## Scripts & Assets\n\n"
            "| `scripts/run.py` | runs the thing | [SRC:src/run.py:L1] |\n\n"
            "Upstream validates with `bmad-module-builder/scripts/validate-module.py`"
            " and `my_scripts/helper.py`, not bundled here.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "scripts").mkdir(parents=True)
            (pkg / "scripts" / "run.py").write_text("x", encoding="utf-8")
            missing, orphans = crossref_section_7b(skill_md, str(pkg))
            assert missing == []
            assert orphans == []

    def test_section_7b_dot_slash_prefix_still_matches(self):
        """A package-relative claim written as ./scripts/… or ./assets/… still counts."""
        skill_md = (
            "# demo\n\n## Scripts & Assets\n\n"
            "Run `./scripts/run.py`; the template is [here](./assets/t.json).\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "scripts").mkdir(parents=True)
            missing, orphans = crossref_section_7b(skill_md, str(pkg))
            assert missing == ["assets/t.json", "scripts/run.py"]
            assert orphans == []

    def test_section_7b_decoy_heading_before_the_real_section(self):
        """A level-3 heading that mentions assets (JavaScript holds "script") is not Section 7b."""
        skill_md = (
            "---\nname: demo\ndescription: A demo skill with a scripts manifest\n---\n\n"
            "# demo\n\n## Usage\n\n### Loading assets from JavaScript\n\n"
            "Load `assets/bunny.png` from your own app at runtime.\n\n"
            "## Scripts & Assets\n\n"
            "| `scripts/build.sh` | builds the demo | [SRC:build.sh:L1] |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, skill_md=skill_md)
            (pkg / "scripts").mkdir()
            (pkg / "scripts" / "build.sh").write_bytes(b"echo build\n")
            r = validate_skill_package(str(pkg), export_gate=True)
            cr = r["validation"]["crossref_7b"]
            assert (cr["missing"], cr["orphans"]) == ([], [])
            assert (cr["heading"], cr["heading_line"]) == ("## Scripts & Assets", 14)
            assert (r["export_status"], r["result"]) == ("READY", "PASS")

    def test_a_shell_comment_in_a_fence_is_not_section_7b(self):
        """A package with no Section 7b whose bash fence names scripts and assets in a comment."""
        skill_md = (
            "---\nname: demo\ndescription: A demo skill without a scripts manifest\n---\n\n"
            "# demo\n\n## Quick Start\n\n```bash\n"
            "# Copy the starter scripts and assets\n"
            "cp ./assets/logo.svg public/\n```\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, skill_md=skill_md)
            r = validate_skill_package(str(pkg), export_gate=True)
            cr = r["validation"]["crossref_7b"]
            assert (cr["missing"], cr["orphans"], cr["heading"], cr["heading_line"]) == ([], [], None, None)
            assert (r["export_status"], r["result"]) == ("READY", "PASS")
            proc = subprocess.run([sys.executable, str(SCRIPT), str(pkg), "--export-gate"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            assert json.loads(proc.stdout)["export_status"] == "READY"

    @pytest.mark.parametrize("heading", ["## 7b. Scripts & Assets", "## 7b Scripts & Assets",
                                         "## Scripts & Assets ##"],
                             ids=["numbered-dot", "numbered", "closing-hashes"])
    def test_section_7b_heading_forms(self, heading):
        skill_md = f"# demo\n\n{heading}\n\n`scripts/run.py`\n\n## Next\n\n`scripts/later.py`\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "scripts").mkdir(parents=True)
            (pkg / "scripts" / "run.py").write_bytes(b"x")
            missing, orphans = crossref_section_7b(skill_md, str(pkg))
            assert (missing, orphans) == ([], []), "the section ends at the next level-2 heading"
            assert mod.section_7b_heading(skill_md) == (heading, 3)

    def test_a_fenced_heading_neither_opens_nor_ends_section_7b(self):
        skill_md = (
            "# demo\n\n```markdown\n## Scripts & Assets\n`assets/example.png`\n```\n\n"
            "## Scripts & Assets\n\n```bash\n## not a heading\n```\n`scripts/run.py`\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "scripts").mkdir(parents=True)
            (pkg / "scripts" / "run.py").write_bytes(b"x")
            missing, orphans = crossref_section_7b(skill_md, str(pkg))
            assert (missing, orphans) == ([], [])
            assert mod.section_7b_heading(skill_md) == ("## Scripts & Assets", 8)

    def test_a_missing_file_names_the_heading_and_its_line(self):
        skill_md = "# demo\n\n## Overview\n\nDemo.\n\n## Scripts & Assets\n\n`scripts/run.py`\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, skill_md=skill_md)
            r = validate_skill_package(str(pkg), export_gate=True)
            [issue] = [i for i in r["validation"]["crossref_7b"]["issues"] if i["severity"] == "high"]
            assert "'## Scripts & Assets' at line 7" in issue["message"] and "scripts/run.py" in issue["message"]
            assert r["export_status"] == "NOT_READY"


class TestExportGateConfidenceTier:
    """--export-gate: the confidence_tier scale depends on skill_type (#552)."""

    def _stack(self, tmp, **meta_overrides):
        return make_stack_package(
            tmp,
            library_count=2,
            ref_libs=["lib-a", "lib-b"],
            catalog=False,
            pair_files=["lib-a-lib-b"],
            integration_count=1,
            confidence_distribution={"t1": 0, "t1_low": 2, "t2": 0, "t3": 0},
            meta_overrides=meta_overrides,
        )

    def test_stack_from_template_passes_gate(self):
        """A stack from the stack template (T-code confidence_tier) is not NOT_READY."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._stack(tmp)
            r = validate_skill_package(str(pkg), export_gate=True)
            meta = r["validation"]["metadata"]
            assert meta["issues"] == [{"severity": "low", "field": "exports", "message": "exports array is empty"}]
            assert meta["enum_issues"] == []
            assert r["summary"]["by_severity"]["high"] == 0
            assert r["result"] == "PASS"
            assert r["export_status"] != "NOT_READY"

    @pytest.mark.parametrize("tier", ["T1", "T1-low", "T2", "T3"])
    def test_stack_accepts_every_t_code(self, tier):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._stack(tmp, confidence_tier=tier, exports=["useStack"])
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["validation"]["metadata"]["enum_issues"] == []
            assert r["export_status"] == "READY"

    @pytest.mark.parametrize("tier", ["Quick", "Forge", "Forge+", "Deep"])
    def test_stack_forge_tier_exports_with_low_note(self, tier):
        """An older stack holds its forge tier in confidence_tier: it still exports, with a low note."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._stack(tmp, confidence_tier=tier, forge_tier=tier, exports=["useStack"])
            r = validate_skill_package(str(pkg), export_gate=True)
            meta = r["validation"]["metadata"]
            assert meta["enum_issues"] == []
            assert meta["recommended_missing"] == []
            assert [(i["severity"], i["field"]) for i in meta["issues"]] == [("low", "confidence_tier")]
            assert f"'{tier}' is a forge tier" in meta["issues"][0]["message"]
            assert "re-run Stack Skill" in meta["issues"][0]["message"]
            assert r["summary"]["by_severity"] == {"high": 0, "medium": 0, "low": 1}
            assert r["result"] == "PASS"
            assert r["export_status"] == "WARNINGS"

    def test_older_stack_passes_the_cli_gate(self):
        """A stack as it sits on disk with confidence_tier and forge_tier "Deep": exit 0, as before."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._stack(tmp, confidence_tier="Deep", forge_tier="Deep")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(pkg), "--export-gate"],
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, proc.stdout
            r = json.loads(proc.stdout)
            assert r["result"] == "PASS"
            assert r["export_status"] == "WARNINGS"
            assert r["validation"]["metadata"]["enum_issues"] == []
            assert sorted(i["field"] for i in r["validation"]["metadata"]["issues"]) == [
                "confidence_tier", "exports"
            ]

    def test_stack_rejects_unknown_tier(self):
        """A value on neither scale is still a high enum issue for a stack."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._stack(tmp, confidence_tier="High")
            r = validate_skill_package(str(pkg), export_gate=True)
            enum_issues = r["validation"]["metadata"]["enum_issues"]
            assert [(i["severity"], i["field"]) for i in enum_issues] == [("high", "confidence_tier")]
            assert "'T1-low'" in enum_issues[0]["message"]
            assert "skill_type 'stack'" in enum_issues[0]["message"]
            assert r["export_status"] == "NOT_READY"

    @pytest.mark.parametrize("tier", ["Quick", "Forge", "Forge+", "Deep"])
    def test_single_accepts_every_forge_tier(self, tier):
        """A forge tier is a single skill's own scale: no enum issue and no note."""
        meta = copy.deepcopy(EXPORT_GATE_META)
        meta["confidence_tier"] = tier
        required_issues, enum_issues, _ = validate_metadata_export_gate(meta)
        assert required_issues == []
        assert enum_issues == []

    @pytest.mark.parametrize("tier", ["T1", "T1-low", "T2", "T3"])
    def test_single_rejects_t_code(self, tier):
        """A single skill's confidence_tier holds the forge tier; a T-code is an enum issue."""
        meta = copy.deepcopy(EXPORT_GATE_META)
        meta["confidence_tier"] = tier
        _, enum_issues, _ = validate_metadata_export_gate(meta)
        assert [(i["severity"], i["field"]) for i in enum_issues] == [("high", "confidence_tier")]
        assert "skill_type 'single'" in enum_issues[0]["message"]

    def test_unknown_skill_type_checks_both_scales(self):
        """With no valid skill_type, a tier from either scale is not flagged again."""
        for tier in ("Forge", "T2"):
            meta = copy.deepcopy(EXPORT_GATE_META)
            meta["skill_type"] = "bogus"
            meta["confidence_tier"] = tier
            _, enum_issues, _ = validate_metadata_export_gate(meta)
            assert [i["field"] for i in enum_issues] == ["skill_type"]

    def test_non_string_skill_type_does_not_crash(self):
        meta = copy.deepcopy(EXPORT_GATE_META)
        meta["skill_type"] = ["single"]
        required_issues, enum_issues, recommended_missing = validate_metadata_export_gate(meta)
        assert [i["field"] for i in required_issues] == ["skill_type"]
        assert enum_issues == []
        assert recommended_missing == []


class TestExportGateRecommendedFields:
    """--export-gate: missing recommended fields, chosen by skill_type (#607)."""

    @pytest.mark.parametrize(
        "field", ["description", "source_repo", "language", "tool_versions", "ast_node_count"]
    )
    def test_single_missing_one_field_warns(self, field):
        """A single skill missing one recommended field -> WARNINGS naming it."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = copy.deepcopy(EXPORT_GATE_META)
            del meta[field]
            pkg = make_export_gate_package(tmp, meta=meta)
            r = validate_skill_package(str(pkg), export_gate=True)
            missing = r["validation"]["metadata"]["recommended_missing"]
            assert [i["field"] for i in missing] == [field]
            assert missing[0]["severity"] == "low"
            assert field in missing[0]["message"]
            assert r["summary"]["by_severity"] == {"high": 0, "medium": 0, "low": 1}
            assert r["export_status"] == "WARNINGS"
            assert r["result"] == "PASS"

    def test_empty_value_counts_as_missing(self):
        """quick-skill writes description "" when none was given: that is missing."""
        meta = copy.deepcopy(EXPORT_GATE_META)
        meta["description"] = ""
        meta["tool_versions"] = {}
        _, _, missing = validate_metadata_export_gate(meta)
        assert [i["field"] for i in missing] == ["description", "tool_versions"]

    def test_complete_quick_skill_ready(self):
        """A complete Quick skill has no ast_node_count and still gets READY."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, meta=copy.deepcopy(QUICK_EXPORT_GATE_META))
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["validation"]["metadata"]["recommended_missing"] == []
            assert r["export_status"] == "READY"

    def test_ast_node_count_expected_only_with_t1(self):
        """ast_node_count is recommended for a single skill only when it counts T1 signatures."""
        meta = copy.deepcopy(EXPORT_GATE_META)
        del meta["ast_node_count"]
        for dist, expected in (
            ({"t1": 3, "t1_low": 0, "t2": 0, "t3": 0}, ["ast_node_count"]),
            ({"t1": 0, "t1_low": 3, "t2": 0, "t3": 0}, []),
            (None, []),
        ):
            meta["confidence_distribution"] = dist
            _, _, missing = validate_metadata_export_gate(meta)
            assert [i["field"] for i in missing] == expected

    def test_stack_from_template_no_recommended_warning(self):
        """A stack with its template fields (no description, source_repo or ast_node_count) is not warned."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_stack_package(
                tmp,
                library_count=2,
                ref_libs=["lib-a", "lib-b"],
                catalog=True,
                pair_files=["lib-a-lib-b"],
                integration_count=1,
                confidence_distribution={"t1": 2, "t1_low": 0, "t2": 0, "t3": 0},
            )
            r = validate_skill_package(str(pkg), export_gate=True)
            meta = json.loads((pkg / "metadata.json").read_text(encoding="utf-8"))
            assert "description" not in meta and "source_repo" not in meta
            assert "ast_node_count" not in meta
            assert r["validation"]["metadata"]["recommended_missing"] == []

    def test_stack_missing_language_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_stack_package(
                tmp,
                library_count=2,
                ref_libs=["lib-a", "lib-b"],
                catalog=False,
                pair_files=["lib-a-lib-b"],
                integration_count=1,
                confidence_distribution={"t1": 0, "t1_low": 2, "t2": 0, "t3": 0},
                meta_overrides={"language": "", "exports": ["useStack"]},
            )
            r = validate_skill_package(str(pkg), export_gate=True)
            missing = r["validation"]["metadata"]["recommended_missing"]
            assert [i["field"] for i in missing] == ["language"]
            assert "stack" in missing[0]["message"]
            assert r["export_status"] == "WARNINGS"

    def test_parse_error_keeps_recommended_key(self):
        """A metadata.json that does not parse still emits an empty recommended_missing."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            pkg.mkdir()
            (pkg / "SKILL.md").write_text(EXPORT_GATE_SKILL_MD, encoding="utf-8")
            (pkg / "metadata.json").write_text("{not valid json", encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["validation"]["metadata"]["recommended_missing"] == []

    @pytest.mark.parametrize(
        "skill_type, templates",
        [
            ("single", ["src/skf-quick-skill/assets/skill-template.md",
                        "src/skf-create-skill/assets/skill-sections.md"]),
            ("stack", ["src/skf-create-stack-skill/assets/stack-skill-template.md"]),
        ],
    )
    def test_recommended_set_matches_generator_templates(self, skill_type, templates):
        """Every recommended field is one each generator's metadata template writes."""
        recommended = set(mod._EXPORT_GATE_RECOMMENDED[skill_type])
        for relpath in templates:
            keys = template_metadata_keys(relpath)
            assert recommended <= keys, f"{relpath} lacks {sorted(recommended - keys)}"
        if skill_type == "stack":
            keys = template_metadata_keys(templates[0])
            assert "description" not in keys and "source_repo" not in keys
