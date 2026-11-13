#!/usr/bin/env python3
"""Tests for skf-validate-output.py."""

from __future__ import annotations

import copy
import json
import re
import shlex
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
# src/skf-create-stack-skill/assets/metadata-contract.md, for a compose-mode
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

- Call `a()` before `b()` (src/app.ts:12).
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

    # -- §4: each Conventions bullet cites what shows it (#1155) -----------------

    @staticmethod
    def _with_conventions(tmp, conventions):
        return make_full_stack(tmp, skill_md=FULL_STACK_HEADER + FULL_STACK_INDEX.replace("{prefix}", "references/")
                               + conventions)

    @pytest.mark.parametrize("bullet", [
        "- Call `a()` before `b()` (src/app.ts:12).",
        "- Call `a()` before `b()` (src/app.ts:12, src/b.ts:4).",
        "1. Call `a()` before `b()` (app/(auth)/page.tsx:3-9).",
        "- Call `a()` before `b()` [from skill: lib-a].",
        "- Call `a()` before `b()`,\n  as the entry point does (src/app.ts:12).",
        "- Call `a()` before `b()` (src/app.ts:12):\n  - in each handler\n  - in each job",
        "- Call `a()` before `b()`.\n\n  The entry point does (src/app.ts:12).",
    ], ids=["code", "comma-separated", "ordered-route-group-range", "compose", "continuation-line", "nested-bullets",
            "loose-item"])
    def test_a_cited_convention_is_no_issue(self, bullet):
        with tempfile.TemporaryDirectory() as tmp:
            assert structure(self._with_conventions(tmp, f"## Conventions\n\n{bullet}\n"))["issues"] == []

    def test_an_uncited_convention_is_a_low_issue(self):
        conventions = ("## Conventions\n\n- Call `a()` before `b()` (src/app.ts:12).\n- Call a() first.\n"
                       "- Keep `b()` last ({file}:{line}).\n- Keep `b()` last [from skill: {name}].\n")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._with_conventions(tmp, conventions)
            issues = issues_by(structure(pkg), "skill_md")
            assert [(i["severity"], i["field"]) for i in issues] == [("low", "conventions")] * 3, issues
            assert '"- Call a() first."' in issues[0]["message"]
            # A template placeholder left unfilled is no citation.
            assert '"- Keep `b()` last ({file}:{line})."' in issues[1]["message"]
            assert '"- Keep `b()` last [from skill: {name}]."' in issues[2]["message"]
            assert "`({file}:{line})` or `[from skill: {name}]`" in issues[0]["message"]
            r = validate_skill_package(str(pkg), skill_type="stack")
            cited = [i for i in r["validation"]["stack_structure"]["issues"] if i["field"] == "conventions"]
            # They count as low issues, and none fails the package.
            assert len(cited) == 3 and r["summary"]["by_severity"]["low"] >= 3 and r["result"] == "PASS"

    @pytest.mark.parametrize("bullet", [
        "* Call a() first.", "+ Call a() first.", "1. Call a() first.", "1) Call a() first.",
        "- Call `fn(x:1)` first.", "- Keep `b()` last ({file}:12).",
    ], ids=["star", "plus", "ordered-dot", "ordered-paren", "code-span", "placeholder-file"])
    def test_each_list_marker_and_a_look_alike_is_checked(self, bullet):
        """An uncited item is flagged whatever its marker, and a `(x:1)` in a code span or a placeholder path is no
        citation."""
        with tempfile.TemporaryDirectory() as tmp:
            issues = issues_by(structure(self._with_conventions(tmp, f"## Conventions\n\n{bullet}\n")), "skill_md")
            assert [(i["severity"], i["field"]) for i in issues] == [("low", "conventions")], issues
            assert f'"{bullet}"' in issues[0]["message"]

    def test_a_nested_bullet_belongs_to_its_parent(self):
        """A sub-bullet is part of its parent's item, so an uncited parent and its sub-bullets are one issue."""
        conventions = "## Conventions\n\n- Call a() first:\n  - in each handler\n"
        with tempfile.TemporaryDirectory() as tmp:
            issues = issues_by(structure(self._with_conventions(tmp, conventions)), "skill_md")
            assert [i["field"] for i in issues] == ["conventions"], issues
            assert '"- Call a() first: - in each handler"' in issues[0]["message"]

    def test_a_fenced_bullet_and_a_plain_line_are_no_conventions(self):
        """A section whose conventions were all dropped keeps one plain line, which cites nothing (compile-stack
        §5), and a bullet inside fenced code is an example, not a convention."""
        conventions = ("## Conventions\n\nNo convention could be cited from the extractions.\n\n"
                       "```markdown\n- Call a() first.\n```\n")
        with tempfile.TemporaryDirectory() as tmp:
            assert structure(self._with_conventions(tmp, conventions))["issues"] == []

    def test_only_the_conventions_section_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._with_conventions(tmp, FULL_STACK_CONVENTIONS + "\n## Notes\n\n- An uncited note.\n")
            assert structure(pkg)["issues"] == []

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
        """Every key the stack metadata contract writes, less ast_node_count and the keys the count pass checks."""
        keys = template_metadata_keys("src/skf-create-stack-skill/assets/metadata-contract.md")
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
            assert "package" not in r
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


COUNT_TOKENS = SCRIPT.parent / "skf-count-tokens.py"
PACKAGE_FIELDS = ["name", "version", "skill_type", "source_authority", "confidence_tier", "forge_tier",
                  "generation_date", "exports_count", "top_exports", "references_count", "components_count",
                  "integrations_count"]


def _count_tokens_module():
    count_spec = importlib.util.spec_from_file_location("skf_count_tokens", COUNT_TOKENS)
    module = importlib.util.module_from_spec(count_spec)
    count_spec.loader.exec_module(module)
    return module


class TestExportGatePackage:
    """--export-gate: the `package` object load-skill.md §3 binds and §5 renders (#1162)."""

    def test_references_count_is_the_token_counters_count(self):
        """Every file under references/, at any depth and of any kind, as skf-count-tokens.py counts them."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp)
            (pkg / "references" / "sub").mkdir(parents=True)
            for rel in ("references/a.md", "references/sub/b.md", "references/data.json"):
                (pkg / rel).write_bytes(b"x\n")
            package = validate_skill_package(str(pkg), export_gate=True)["package"]
            assert package["references_count"] == 3
            counted = _count_tokens_module().count_package(pkg)["references_total"]["count"]
            assert package["references_count"] == counted

    def test_no_references_folder_counts_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp)
            package = validate_skill_package(str(pkg), export_gate=True)["package"]
            assert package["references_count"] == 0
            assert _count_tokens_module().count_package(pkg)["references_total"]["count"] == 0

    def test_a_single_skill_gives_its_metadata_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = validate_skill_package(str(make_export_gate_package(tmp)), export_gate=True)
            assert list(r["package"]) == PACKAGE_FIELDS
            assert r["package"] == {
                "name": "demo", "version": "1.0.0", "skill_type": "single", "source_authority": "community",
                "confidence_tier": "Forge+", "forge_tier": None, "generation_date": "2026-07-13",
                "exports_count": 2, "top_exports": ["foo", "bar"], "references_count": 0,
                "components_count": None, "integrations_count": None,
            }

    def test_mixed_exports_give_the_count_and_the_first_five_names(self):
        """Strings and `{name, type}` dicts; a dict without a string `name` is skipped."""
        meta = copy.deepcopy(EXPORT_GATE_META)
        meta["exports"] = ["z", {"name": "ZodType", "type": "class"}, {"type": "function"}, {"name": 7},
                           "parse", {"name": "safeParse", "type": "function"}, "infer", "extra"]
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert package["exports_count"] == 8
            assert package["top_exports"] == ["z", "ZodType", "parse", "safeParse", "infer"]

    def test_seven_exports_list_five(self):
        meta = copy.deepcopy(EXPORT_GATE_META)
        meta["exports"] = ["a", {"name": "b", "type": "class"}, "c", {"name": "d", "type": "type"}, "e", "f", "g"]
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert (package["exports_count"], package["top_exports"]) == (7, ["a", "b", "c", "d", "e"])

    def test_a_stack_gives_its_library_and_integration_counts(self):
        meta = dict(STACK_TEMPLATE_META, library_count=3, integration_count=2)
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert (package["components_count"], package["integrations_count"]) == (3, 2)
            assert (package["confidence_tier"], package["forge_tier"]) == ("T1-low", "Deep")

    def test_a_stack_without_counts_falls_back_to_its_lists(self):
        meta = {k: v for k, v in STACK_TEMPLATE_META.items() if k not in ("library_count", "integration_count")}
        meta["libraries"] = ["lib-a", "lib-b", "lib-c"]
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert (package["components_count"], package["integrations_count"]) == (3, 1)
            meta["library_count"] = "3"  # not an int: the list decides
            pkg = make_export_gate_package(tmp, meta=meta, name="other")
            assert validate_skill_package(str(pkg), export_gate=True)["package"]["components_count"] == 3

    def test_a_stack_with_neither_key_nor_list_counts_null(self):
        meta = {k: v for k, v in STACK_TEMPLATE_META.items()
                if k not in ("library_count", "integration_count", "libraries", "integration_pairs")}
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert (package["components_count"], package["integrations_count"]) == (None, None)

    def test_a_single_skill_has_no_stack_counts(self):
        meta = dict(EXPORT_GATE_META, library_count=3, integration_count=2)
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert (package["components_count"], package["integrations_count"]) == (None, None)

    @pytest.mark.parametrize("text", [None, "{not valid json", "[]"], ids=["missing", "not-json", "not-an-object"])
    def test_broken_metadata_gives_null_fields_and_still_counts_references(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "demo"
            (pkg / "references").mkdir(parents=True)
            (pkg / "references" / "a.md").write_bytes(b"x\n")
            (pkg / "SKILL.md").write_text(EXPORT_GATE_SKILL_MD, encoding="utf-8")
            if text is not None:
                (pkg / "metadata.json").write_text(text, encoding="utf-8")
            r = validate_skill_package(str(pkg), export_gate=True)
            assert r["export_status"] == "NOT_READY"
            assert list(r["package"]) == PACKAGE_FIELDS
            assert r["package"] == {field: None for field in PACKAGE_FIELDS} | {"references_count": 1}

    def test_a_field_metadata_lacks_is_null(self):
        meta = copy.deepcopy(EXPORT_GATE_META)
        del meta["generation_date"]
        meta["version"] = 3
        meta["exports"] = "foo"
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert (package["generation_date"], package["version"]) == (None, None)
            assert (package["exports_count"], package["top_exports"]) == (None, None)

    @pytest.mark.parametrize("value", ["", "  "], ids=["empty", "whitespace"])
    def test_a_required_text_field_is_null_only_when_the_gate_flags_it(self, value):
        """The gate and `package` read a required field with one test, so a passed package names its version."""
        meta = dict(EXPORT_GATE_META, version=value)
        with tempfile.TemporaryDirectory() as tmp:
            r = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)
            flagged = {i["field"] for i in r["validation"]["metadata"]["issues"] if i["severity"] == "high"}
            assert (r["package"]["version"] is None) == ("version" in flagged)
            assert r["package"]["version"] == (None if value == "" else value)

    def test_a_blank_forge_tier_and_blank_export_names_are_left_out(self):
        meta = dict(STACK_TEMPLATE_META, forge_tier="", exports=["", " ", "z", {"name": " "}])
        with tempfile.TemporaryDirectory() as tmp:
            package = validate_skill_package(str(make_export_gate_package(tmp, meta=meta)), export_gate=True)["package"]
            assert package["forge_tier"] is None
            assert (package["exports_count"], package["top_exports"]) == (4, ["z"])

    def test_a_bool_library_count_is_not_a_count(self):
        """`library_count: true` is no count of 1: the `libraries` list decides, else null."""
        meta = {k: v for k, v in STACK_TEMPLATE_META.items() if k not in ("libraries", "library_count")}
        meta["library_count"] = True
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp, meta=meta)
            assert validate_skill_package(str(pkg), export_gate=True)["package"]["components_count"] is None
            meta["libraries"] = ["lib-a", "lib-b"]
            pkg = make_export_gate_package(tmp, meta=meta, name="other")
            assert validate_skill_package(str(pkg), export_gate=True)["package"]["components_count"] == 2

    def test_the_cli_prints_the_package_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = make_export_gate_package(tmp)
            proc = subprocess.run([sys.executable, str(SCRIPT), str(pkg), "--export-gate"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            out = json.loads(proc.stdout)
            assert out["package"] == validate_skill_package(str(pkg), export_gate=True)["package"]


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
            ("stack", ["src/skf-create-stack-skill/assets/metadata-contract.md"]),
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


# --- Snippet length bounds (#812) -------------------------------------------

STACK_VALIDATE_MD = Path(__file__).parent.parent / "src" / "skf-create-stack-skill" / "references" / "validate.md"
GENERATE_SNIPPET_MD = Path(__file__).parent.parent / "src" / "skf-export-skill" / "references" / "generate-snippet.md"
SNIPPET_FORMAT_MD = Path(__file__).parent.parent / "src" / "skf-export-skill" / "assets" / "snippet-format.md"


def _two_line_snippet(tokens: int) -> str:
    """A two-line context snippet whose `len(text)//4` estimate is exactly `tokens`."""
    head = "[demo v1.0.0]|root: .claude/skills/demo/\n|IMPORTANT: demo v1.0.0: read SKILL.md before writing demo code. "
    snippet = head + "x" * (tokens * 4 - len(head) - 1) + "\n"
    assert snippet.count("\n") == 2 and len(snippet) // 4 == tokens
    return snippet


def _length_issues(tokens: int) -> list[dict]:
    return [i for i in mod.validate_context_snippet(_two_line_snippet(tokens)) if i["field"] == "length"]


class TestSnippetLengthBounds:
    """The long-snippet warning is generate-snippet §4's 300-token ceiling, not 200."""

    def test_a_250_token_snippet_is_not_flagged(self):
        assert _length_issues(250) == []

    def test_a_301_token_snippet_is_flagged_low_naming_the_ceiling(self):
        assert mod.SNIPPET_TOKEN_CEILING == 300
        assert _length_issues(300) == []
        [issue] = _length_issues(301)
        assert issue["severity"] == "low" and "300-token ceiling" in issue["message"]
        # create-stack-skill's validate step quotes the validator's bounds.
        text = STACK_VALIDATE_MD.read_text(encoding="utf-8")
        assert "<40 / >300" in text and ">200" not in text

    def test_a_39_token_snippet_is_still_too_short(self):
        assert mod.SNIPPET_TOKEN_FLOOR == 40
        assert _length_issues(40) == []
        [issue] = _length_issues(39)
        assert issue["severity"] == "low" and "too short" in issue["message"]

    def test_generate_snippet_states_the_validator_ceiling(self):
        text = GENERATE_SNIPPET_MD.read_text(encoding="utf-8")
        [ceiling] = re.findall(r"^- Hard ceiling: (\d+) tokens", text, re.MULTILINE)
        assert int(ceiling) == mod.SNIPPET_TOKEN_CEILING
        [trim] = re.findall(r"^- If `\{count\}` is above (\d+),.*?until `\{count\}` is (\d+) or below", text, re.MULTILINE)
        assert {int(n) for n in trim} == {mod.SNIPPET_TOKEN_CEILING}

    def test_only_generate_snippet_states_the_validator_ceiling(self):
        """#1164: the token target and ceiling live in generate-snippet §4 alone; the snippet format states no
        token number, so no second copy can drift from the validator."""
        text = GENERATE_SNIPPET_MD.read_text(encoding="utf-8")
        [target] = re.findall(r"^- Target: ~(\d+)-(\d+) tokens per skill", text, re.MULTILINE)
        assert [int(n) for n in target] == [80, 120]
        assert text.count("80-120") == 1, "the STEP GOAL no longer restates §4's target"
        assert "drop api names from the end of the §3b ranking" in text
        fmt = SNIPPET_FORMAT_MD.read_text(encoding="utf-8")
        assert not re.search(r"\btokens?\b|\b\d+-token\b", fmt), "the snippet format states no token budget"


# --- #1166 determinism-1: --snippet-check, the draft check generate-snippet §4 runs ---------

REBUILD_SCRIPT = SCRIPT.parent / "skf-rebuild-managed-sections.py"
EM_DASH = chr(0x2014)  # the snippet format's IMPORTANT and key-types lines carry one
CHECK_SKILL_MD = """---
name: zod
description: Zod schemas
# a YAML comment is no heading
---

# zod

## Quick Start

```ts
## Not A Heading
```

## Usage

## Usage

## Key Types (Quick Start Essentials)
"""
CHECK_DRAFT = (
    "[zod v4.1.0]|root: .claude/skills/zod/\n"
    "|IMPORTANT: zod v4.1.0 " + EM_DASH + " read SKILL.md before writing zod code. Do NOT rely on training data.\n"
    "|quick-start:SKILL.md#quick-start\n"
    "|api: parse(), safeParse(), z\n"
    "|key-types:SKILL.md#key-types-quick-start-essentials " + EM_DASH + " ZodType, infer, ZodError\n"
    "|gotchas: `parse()` throws on an unknown key since v4\n"
)
# Each bad draft of the matrix: the change, and the high issue it raises.
BAD_DRAFTS = {
    "version": (("[zod v4.1.0]", "[zod v4.0.0]"), "header"),
    "name": (("[zod v4.1.0]", "[yup v4.1.0]"), "header"),
    "blank": (("|quick-start:", "\n|quick-start:"), "separator"),
    "bare-pipe": (("|quick-start:", "|\n|quick-start:"), "separator"),
    "marker": (("|api: ", "|api: <!--SKF:END--> "), "marker"),
    "no-heading": (("SKILL.md#quick-start", "SKILL.md#getting-started"), "anchor"),
    "no-file": (("SKILL.md#quick-start", "references/full.md#quick-start"), "anchor"),
    "dot-dot": (("SKILL.md#quick-start", "references/../SKILL.md#quick-start"), "anchor"),
}


def make_snippet_case(tmpdir, draft=CHECK_DRAFT, *, meta=None, full=None):
    """A `zod` package and a draft folder holding `draft` as context-snippet.md."""
    pkg = Path(tmpdir) / "skills" / "zod" / "4.1.0" / "zod"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(CHECK_SKILL_MD, encoding="utf-8")
    (pkg / "metadata.json").write_text(json.dumps(meta or {"name": "zod", "version": "4.1.0"}), encoding="utf-8")
    if full is not None:
        (pkg / "references").mkdir()
        (pkg / "references" / "full.md").write_text(full, encoding="utf-8")
    drafts = Path(tmpdir) / "stage" / "drafts"
    (drafts / "zod").mkdir(parents=True)
    if draft is not None:
        (drafts / "zod" / "context-snippet.md").write_bytes(draft.encode("utf-8") if isinstance(draft, str) else draft)
    return drafts / "zod", pkg


def run_snippet_check(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def high_fields(result):
    return [i["field"] for i in result["issues"] if i["severity"] == "high"]


class TestSnippetCheck:
    def test_heading_slugs_are_githubs(self):
        text = ("---\nname: x\n# not a heading\n---\n# A B\n## A B\n## A-B!\n```\n# fenced\n```\n"
                "### Key Types (Quick Start Essentials)\n#### Ünïcode_x `code`\n")
        assert mod.heading_slugs(text) == ["a-b", "a-b-1", "a-b-2", "key-types-quick-start-essentials",
                                           "ünïcode_x-code"]

    def test_a_good_draft_passes_in_process_and_through_the_cli(self, tmp_path):
        draft, pkg = make_snippet_case(tmp_path)
        result = mod.check_snippet_draft(draft, pkg)
        assert (result["result"], result["issues"]) == ("PASS", [])
        assert (result["mode"], result["skill_name"], result["version"]) == ("snippet-check", "zod", "4.1.0")
        proc = run_snippet_check(draft, "--snippet-check", "--package", pkg)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        out = json.loads(proc.stdout)
        assert (Path(out["draft"]), Path(out["package"])) == (draft, pkg)
        assert out["summary"] == {"total_issues": 0, "by_severity": {"high": 0, "medium": 0, "low": 0}}

    @pytest.mark.parametrize("case", sorted(BAD_DRAFTS))
    def test_a_bad_draft_fails_with_a_high_issue(self, tmp_path, case):
        (old, new), field = BAD_DRAFTS[case]
        assert CHECK_DRAFT.count(old) == 1
        draft, pkg = make_snippet_case(tmp_path, CHECK_DRAFT.replace(old, new))
        result = mod.check_snippet_draft(draft, pkg)
        assert result["result"] == "FAIL" and field in high_fields(result), result["issues"]
        proc = run_snippet_check(draft, "--snippet-check", "--package", pkg)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["issues"] == result["issues"]
        if field == "separator":
            [issue] = [i for i in result["issues"] if i["field"] == "separator"]
            assert issue["message"].startswith("line 3 is blank or a bare `|`"), issue

    def test_a_split_body_anchor_and_a_repeated_heading_resolve(self, tmp_path):
        draft = CHECK_DRAFT.replace("SKILL.md#quick-start", "references/full.md#quick-start") \
            + "|usage:SKILL.md#usage-1\n"
        draft_dir, pkg = make_snippet_case(tmp_path, draft, full="# Full\n\n## Quick Start\n")
        assert mod.check_snippet_draft(draft_dir, pkg)["result"] == "PASS"
        # A third Usage heading does not exist.
        (draft_dir / "context-snippet.md").write_text(draft.replace("#usage-1", "#usage-2"), encoding="utf-8")
        result = mod.check_snippet_draft(draft_dir, pkg)
        assert high_fields(result) == ["anchor"] and "usage-2" in result["issues"][0]["message"]

    def test_an_anchor_ends_at_its_slug(self, tmp_path):
        """The template's `{SKILL.md#quick-start}` braces and a sentence's closing `.` are not part of the slug,
        and generate-snippet §3b states the slug rule the check uses."""
        draft = (CHECK_DRAFT.replace("SKILL.md#quick-start", "{SKILL.md#quick-start}")
                 .replace("since v4\n", "since v4, see SKILL.md#usage.\n"))
        draft_dir, pkg = make_snippet_case(tmp_path, draft)
        assert mod.check_snippet_draft(draft_dir, pkg)["result"] == "PASS"
        (draft_dir / "context-snippet.md").write_text(draft.replace("#quick-start}", "#getting-started}"),
                                                      encoding="utf-8")
        result = mod.check_snippet_draft(draft_dir, pkg)
        assert high_fields(result) == ["anchor"]
        assert result["issues"][0]["message"].endswith("has no heading whose slug is getting-started")
        text = GENERATE_SNIPPET_MD.read_text(encoding="utf-8")
        assert ("heading slugs for `#quick-start` and `#key-types` (GitHub's slug, which §4's check uses: the heading "
                "text lowercased, each character that is not a letter, digit, space, `-` or `_` dropped, each space "
                "made `-`, and `-1` or `-2` added for the second or third heading with the same slug)") in text

    def test_the_format_checks_of_validate_context_snippet_come_first(self, tmp_path):
        """A medium line-2 issue fails the draft; a low length note alone does not."""
        draft, pkg = make_snippet_case(tmp_path, CHECK_DRAFT.replace("|IMPORTANT:", "|NOTE:"))
        result = mod.check_snippet_draft(draft, pkg)
        assert [(i["severity"], i["field"]) for i in result["issues"]] == [("medium", "line2")]
        assert result["result"] == "FAIL"
        short = "[zod v4.1.0]|root: .claude/skills/zod/\n|IMPORTANT: zod v4.1.0\n"
        (draft / "context-snippet.md").write_text(short, encoding="utf-8")
        result = mod.check_snippet_draft(draft, pkg)
        assert [(i["severity"], i["field"]) for i in result["issues"]] == [("low", "length")]
        assert result["result"] == "PASS"

    @pytest.mark.parametrize("state", ["missing", "folder", "not-utf8"])
    def test_a_draft_it_cannot_read_is_a_content_issue(self, tmp_path, state):
        draft, pkg = make_snippet_case(tmp_path, None if state != "not-utf8" else b"[zod v4.1.0]\xff\xfe\n")
        if state == "folder":
            (draft / "context-snippet.md").mkdir()
        result = mod.check_snippet_draft(draft, pkg)
        assert high_fields(result) == ["content"] and result["result"] == "FAIL"
        assert run_snippet_check(draft, "--snippet-check", "--package", pkg).returncode == 1

    def test_a_package_with_no_version_fails_the_header(self, tmp_path):
        draft, pkg = make_snippet_case(tmp_path, meta={"name": "zod"})
        result = mod.check_snippet_draft(draft, pkg)
        assert high_fields(result) == ["header"] and result["version"] is None

    @pytest.mark.parametrize("package", ["none", "no-value", "a-file", "missing"])
    def test_a_package_that_is_no_folder_is_a_usage_error(self, tmp_path, package):
        draft, pkg = make_snippet_case(tmp_path)
        tail = {"none": [], "no-value": ["--package"], "a-file": ["--package", pkg / "metadata.json"],
                "missing": ["--package", tmp_path / "nowhere"]}[package]
        proc = run_snippet_check(draft, "--snippet-check", *tail)
        assert proc.returncode == 2 and proc.stdout == ""
        assert proc.stderr.startswith("error: "), proc.stderr

    @pytest.mark.parametrize("case", ["good", "marker"])
    def test_the_documented_section_4_call(self, tmp_path, case):
        """generate-snippet §4's command, its placeholders filled, checks the staged draft."""
        section = GENERATE_SNIPPET_MD.read_text(encoding="utf-8")
        section = section[section.index("### 4. Verify Token Count"):section.index("### 5. ")]
        [command] = [line for line in section.splitlines() if "--snippet-check" in line and line.startswith("python3")]
        draft = CHECK_DRAFT if case == "good" else CHECK_DRAFT.replace(*BAD_DRAFTS["marker"][0])
        draft_dir, pkg = make_snippet_case(tmp_path, draft)
        values = {"validateOutputHelper": SCRIPT.as_posix(), "export_stage_dir": (tmp_path / "stage").as_posix(),
                  "skill-name": "zod", "resolved_skill_package": pkg.as_posix()}
        filled = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], command)
        words = shlex.split(filled)
        assert words[0] == "python3"
        proc = subprocess.run([sys.executable, *words[1:]], capture_output=True, text=True, encoding="utf-8",
                              timeout=60)
        assert proc.returncode == (0 if case == "good" else 1), proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["result"] == ("PASS" if case == "good" else "FAIL")
        # One corrected retry, then the §4 halt, which takes no new halt reason.
        assert "When it exits non-zero, correct the draft as each high or medium issue says" in section
        assert ('When it fails again, delete the `{export_stage_dir}` folder and HALT (exit code 4, '
                '`halt_reason: "context-rebuild-failed"`, phase `generate-snippet §4`)') in section
        assert "emit warning (code `snippet_trimmed`)" in section

    @pytest.mark.parametrize("case", ["good", "marker", "name"])
    def test_the_check_and_assemble_agree_on_a_draft(self, tmp_path, case):
        """A draft the check passes is a row `assemble --snippet-dir` lists; one it fails, assemble refuses too."""
        spec = importlib.util.spec_from_file_location("skf_rms_snippet_check", REBUILD_SCRIPT)
        rms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rms)
        draft = CHECK_DRAFT if case == "good" else CHECK_DRAFT.replace(*BAD_DRAFTS[case][0])
        draft_dir, pkg = make_snippet_case(tmp_path, draft)
        check = mod.check_snippet_draft(draft_dir, pkg)
        out = rms.cmd_assemble(str(tmp_path / "CLAUDE.md"), str(tmp_path / "skills"), ".claude/skills/",
                               includes=[("zod", "4.1.0")], snippet_dir=str(draft_dir.parent),
                               out=str(tmp_path / "stage" / "previews" / "CLAUDE.md.skf-content"))
        assert out["status"] == "ok", out
        if case == "good":
            assert check["result"] == "PASS"
            assert [i["skill_name"] for i in out["included"]] == ["zod"] and out["skipped_malformed_snippet"] == []
        else:
            assert check["result"] == "FAIL"
            assert [s["skill_name"] for s in out["skipped_malformed_snippet"]] == ["zod"]
