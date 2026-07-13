#!/usr/bin/env python3
"""Tests for skf-validate-output.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import importlib.util
import pytest

spec = importlib.util.spec_from_file_location(
    "skf_validate_output",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-validate-output.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_skill_package = mod.validate_skill_package
validate_stack_counts = mod.validate_stack_counts
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


def make_stack_package(tmpdir, *, library_count, ref_libs, catalog, pair_files,
                       integration_count, confidence_distribution, name="demo-stack"):
    """Build a stack skill package fixture on disk.

    ref_libs: list of per-library reference basenames (without .md).
    catalog: if True, also write references/stack-catalog.md (must NOT be counted).
    pair_files: list of integration pair basenames (without .md).
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
    meta = {
        "name": name,
        "skill_type": "stack",
        "version": "1.0.0",
        "generation_date": "2026-07-13",
        "library_count": library_count,
        "integration_count": integration_count,
        "confidence_distribution": confidence_distribution,
    }
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


# --- Export-gate mode ------------------------------------------------------

EXPORT_GATE_META = {
    "name": "demo",
    "version": "1.0.0",
    "skill_type": "stack",
    "source_authority": "community",
    "exports": ["foo", "bar"],
    "generation_date": "2026-07-13",
    "confidence_tier": "Forge+",
}

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
    m = dict(EXPORT_GATE_META) if meta is None else meta
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
            # No enum or crossref issues on a clean package.
            assert r["validation"]["metadata"]["enum_issues"] == []
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
        required_issues, enum_issues = validate_metadata_export_gate(meta)
        assert required_issues == []
        enum_fields = {i["field"] for i in enum_issues}
        assert enum_fields == {"skill_type", "source_authority", "confidence_tier"}
        assert all(i["severity"] == "high" for i in enum_issues)

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
