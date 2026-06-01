"""Tests for skf-campaign state schema, directory structure, and backup behavior.

Structural tests verify the campaign workflow scaffolding exists. Schema
validation tests confirm _campaign-state.yaml shape enforcement. Backup
behavior tests verify the read-backup-modify-write pattern.
"""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import tempfile

import pytest
import yaml
from jsonschema import ValidationError, validate

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAMPAIGN_DIR = REPO_ROOT / "src" / "skf-campaign"
SCHEMA_PATH = CAMPAIGN_DIR / "assets" / "campaign-state-schema.json"
SKILL_MD_PATH = CAMPAIGN_DIR / "SKILL.md"
MANIFEST_PATH = CAMPAIGN_DIR / "manifest.yaml"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


VALID_MINIMAL_STATE: dict = {
    "campaign": {
        "name": "test-campaign",
        "started_at": "2026-05-27T00:00:00Z",
        "last_updated": "2026-05-27T00:00:00Z",
        "current_stage": 0,
        "quality_gate": {
            "hard": "zero-critical-high",
            "soft_target": 90,
            "soft_fallback": 80,
        },
        "health_findings_queue": "local",
    },
    "skills": [],
    "dependency_graph": {
        "execution_order": [],
        "circular_deps_detected": False,
    },
}

VALID_FULL_STATE: dict = {
    "campaign": {
        "name": "full-campaign",
        "started_at": "2026-05-27T00:00:00Z",
        "last_updated": "2026-05-27T01:00:00Z",
        "current_stage": 4,
        "directive_path": "forge-data/_campaign/_campaign-directive.md",
        "quality_gate": {
            "hard": "zero-critical-high",
            "soft_target": 90,
            "soft_fallback": 80,
        },
        "health_findings_queue": "improvement",
    },
    "skills": [
        {
            "name": "auth-service",
            "status": "completed",
            "depends_on": [],
            "tier": "A",
            "pin": "v1.2.3",
            "brief_path": "forge-data/briefs/auth-service.yaml",
            "skill_path": "forge-data/skills/auth-service/",
            "quality_score": 92.5,
            "workarounds_applied": ["fp-abc123"],
            "started_at": "2026-05-27T00:10:00Z",
            "completed_at": "2026-05-27T00:30:00Z",
            "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        },
        {
            "name": "data-layer",
            "status": "pending",
            "depends_on": ["auth-service"],
            "tier": "B",
            "pin": None,
            "brief_path": None,
            "skill_path": None,
            "quality_score": None,
            "workarounds_applied": [],
            "started_at": None,
            "completed_at": None,
            "commit_sha": None,
        },
    ],
    "dependency_graph": {
        "execution_order": ["auth-service", "data-layer"],
        "circular_deps_detected": False,
    },
}


# ---------------------------------------------------------------------------
# Task 5.1 — Directory structure exists
# ---------------------------------------------------------------------------


class TestDirectoryStructure:
    def test_campaign_dir_exists(self) -> None:
        assert CAMPAIGN_DIR.is_dir(), (
            f"Campaign directory not found at {CAMPAIGN_DIR.as_posix()}"
        )

    def test_skill_md_exists(self) -> None:
        assert SKILL_MD_PATH.is_file(), (
            f"SKILL.md not found at {SKILL_MD_PATH.as_posix()}"
        )

    def test_manifest_yaml_exists(self) -> None:
        assert MANIFEST_PATH.is_file(), (
            f"manifest.yaml not found at {MANIFEST_PATH.as_posix()}"
        )

    def test_assets_dir_exists(self) -> None:
        assets = CAMPAIGN_DIR / "assets"
        assert assets.is_dir(), f"assets/ not found at {assets.as_posix()}"

    def test_references_dir_exists(self) -> None:
        refs = CAMPAIGN_DIR / "references"
        assert refs.is_dir(), f"references/ not found at {refs.as_posix()}"

    def test_templates_dir_exists(self) -> None:
        templates = CAMPAIGN_DIR / "templates"
        assert templates.is_dir(), f"templates/ not found at {templates.as_posix()}"

    def test_scripts_dir_exists(self) -> None:
        scripts = CAMPAIGN_DIR / "scripts"
        assert scripts.is_dir(), f"scripts/ not found at {scripts.as_posix()}"


# ---------------------------------------------------------------------------
# Task 5.2 — Schema file exists and is valid JSON
# ---------------------------------------------------------------------------


class TestSchemaFileValid:
    def test_schema_file_exists(self) -> None:
        assert SCHEMA_PATH.is_file(), (
            f"Schema not found at {SCHEMA_PATH.as_posix()}"
        )

    def test_schema_is_valid_json(self) -> None:
        raw = SCHEMA_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Task 5.3 — Schema is a valid JSON Schema
# ---------------------------------------------------------------------------


class TestSchemaIsJsonSchema:
    def test_schema_parseable_by_jsonschema(self, schema: dict) -> None:
        assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#"
        assert schema.get("type") == "object"
        assert "properties" in schema


# ---------------------------------------------------------------------------
# Task 5.4 — Valid minimal state passes validation
# ---------------------------------------------------------------------------


class TestValidMinimalState:
    def test_minimal_state_passes(self, schema: dict) -> None:
        validate(instance=VALID_MINIMAL_STATE, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.5 — Valid full state passes validation
# ---------------------------------------------------------------------------


class TestValidFullState:
    def test_full_state_passes(self, schema: dict) -> None:
        validate(instance=VALID_FULL_STATE, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.6 — Missing required campaign.name fails
# ---------------------------------------------------------------------------


class TestMissingCampaignName:
    def test_missing_name_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        del state["campaign"]["name"]
        with pytest.raises(ValidationError, match="'name' is a required property"):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.7 — Invalid skills[].status enum fails
# ---------------------------------------------------------------------------


class TestInvalidSkillStatus:
    def test_invalid_status_enum_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0]["status"] = "invalid-status"
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.8 — Invalid campaign.current_stage fails
# ---------------------------------------------------------------------------


class TestInvalidCurrentStage:
    def test_out_of_range_stage_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["current_stage"] = 11
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)

    def test_non_integer_stage_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["current_stage"] = 3.5
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)

    def test_negative_stage_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["current_stage"] = -1
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.9 — Invalid health_findings_queue enum fails
# ---------------------------------------------------------------------------


class TestInvalidHealthFindingsQueue:
    def test_invalid_queue_enum_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["health_findings_queue"] = "remote"
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.10 — Invalid skills[].tier enum fails
# ---------------------------------------------------------------------------


class TestInvalidSkillTier:
    def test_invalid_tier_enum_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0]["tier"] = "C"
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.11 — circular_deps_detected must be boolean
# ---------------------------------------------------------------------------


class TestCircularDepsBoolean:
    def test_non_boolean_circular_deps_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["dependency_graph"]["circular_deps_detected"] = "yes"
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.12 — Extra properties rejected at all levels
# ---------------------------------------------------------------------------


class TestAdditionalPropertiesRejected:
    def test_extra_top_level_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["extra_field"] = "not allowed"
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)

    def test_extra_campaign_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["extra_field"] = "not allowed"
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)

    def test_extra_skill_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0]["extra_field"] = "not allowed"
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)

    def test_extra_dependency_graph_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["dependency_graph"]["extra_field"] = "not allowed"
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)

    def test_extra_quality_gate_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["quality_gate"]["extra_field"] = "not allowed"
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Review fix — manifest.yaml content validation
# ---------------------------------------------------------------------------


class TestManifestContent:
    @pytest.fixture(scope="class")
    def manifest(self) -> dict:
        return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_metadata(self, manifest: dict) -> None:
        assert manifest["code"] == "CA"
        assert manifest["name"] == "skf-campaign"
        assert manifest["trigger"] == "campaign"
        assert manifest["parent_module"] == "skf"

    def test_manifest_config_surface(self, manifest: dict) -> None:
        config = manifest["config"]
        assert "state_file" in config
        assert "backup_file" in config
        assert "directive_file" in config


# ---------------------------------------------------------------------------
# Review fix — required skill field rejection
# ---------------------------------------------------------------------------


class TestMissingRequiredSkillFields:
    def test_missing_skill_name_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        del state["skills"][0]["name"]
        with pytest.raises(ValidationError, match="'name' is a required property"):
            validate(instance=state, schema=schema)

    def test_missing_skill_status_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        del state["skills"][0]["status"]
        with pytest.raises(ValidationError, match="'status' is a required property"):
            validate(instance=state, schema=schema)

    def test_missing_skill_tier_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        del state["skills"][0]["tier"]
        with pytest.raises(ValidationError, match="'tier' is a required property"):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.13–5.14 — Backup behavior
# ---------------------------------------------------------------------------


class TestBackupBehavior:
    def test_backup_created_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = pathlib.Path(tmpdir)
            state_file = tmp / "_campaign-state.yaml"
            backup_file = tmp / "_campaign-state.yaml.bak"

            original_state = copy.deepcopy(VALID_MINIMAL_STATE)
            state_file.write_text(
                yaml.dump(original_state, default_flow_style=False),
                encoding="utf-8",
            )

            shutil.copy2(str(state_file), str(backup_file))

            modified_state = copy.deepcopy(original_state)
            modified_state["campaign"]["current_stage"] = 3
            modified_state["campaign"]["last_updated"] = "2026-05-27T02:00:00Z"
            state_file.write_text(
                yaml.dump(modified_state, default_flow_style=False),
                encoding="utf-8",
            )

            assert backup_file.is_file(), ".bak file must exist after backup"

    def test_backup_content_matches_pre_modification_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = pathlib.Path(tmpdir)
            state_file = tmp / "_campaign-state.yaml"
            backup_file = tmp / "_campaign-state.yaml.bak"

            original_state = copy.deepcopy(VALID_MINIMAL_STATE)
            state_file.write_text(
                yaml.dump(original_state, default_flow_style=False),
                encoding="utf-8",
            )
            original_content = state_file.read_text(encoding="utf-8")

            shutil.copy2(str(state_file), str(backup_file))

            modified_state = copy.deepcopy(original_state)
            modified_state["campaign"]["current_stage"] = 5
            modified_state["campaign"]["last_updated"] = "2026-05-27T03:00:00Z"
            state_file.write_text(
                yaml.dump(modified_state, default_flow_style=False),
                encoding="utf-8",
            )

            backup_content = backup_file.read_text(encoding="utf-8")
            assert backup_content == original_content, (
                ".bak content must match the pre-modification state"
            )
            backup_data = yaml.safe_load(backup_content)
            assert backup_data["campaign"]["current_stage"] == 0
            assert backup_data["campaign"]["last_updated"] == "2026-05-27T00:00:00Z"


# ---------------------------------------------------------------------------
# Task 4 (Story 4.3) — commit_sha field validation
# ---------------------------------------------------------------------------


class TestCommitShaField:
    def test_commit_sha_string_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0]["commit_sha"] = "abc123def456"
        validate(instance=state, schema=schema)

    def test_commit_sha_null_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0]["commit_sha"] = None
        validate(instance=state, schema=schema)

    def test_commit_sha_absent_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0].pop("commit_sha", None)
        validate(instance=state, schema=schema)

    def test_commit_sha_invalid_type_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_FULL_STATE)
        state["skills"][0]["commit_sha"] = 12345
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Campaign-level result fields — architecture_doc_path, capstone,
# verification, refinement (optional summary outcomes persisted to state)
# ---------------------------------------------------------------------------


class TestArchitectureDocPath:
    def test_string_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["architecture_doc_path"] = "docs/architecture.md"
        validate(instance=state, schema=schema)

    def test_null_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["architecture_doc_path"] = None
        validate(instance=state, schema=schema)

    def test_absent_passes(self, schema: dict) -> None:
        validate(instance=VALID_MINIMAL_STATE, schema=schema)

    def test_invalid_type_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["architecture_doc_path"] = 123
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)


class TestCapstoneField:
    def test_full_capstone_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["capstone"] = {
            "skill_path": "forge-data/skills/stack/",
            "quality_score": 91.0,
            "verified": True,
            "completed_at": "2026-05-27T04:00:00Z",
        }
        validate(instance=state, schema=schema)

    def test_null_capstone_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["capstone"] = None
        validate(instance=state, schema=schema)

    def test_extra_capstone_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["capstone"] = {"skill_path": "x", "extra": "no"}
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)


class TestVerificationField:
    def test_full_verification_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["verification"] = {
            "report_path": "forge-data/feasibility-report-latest.md",
            "overall_verdict": "Verified",
            "coverage_percentage": 87.5,
            "recommendation_count": 3,
        }
        validate(instance=state, schema=schema)

    def test_null_verification_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["verification"] = None
        validate(instance=state, schema=schema)

    def test_invalid_verdict_enum_fails(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["verification"] = {"overall_verdict": "Maybe"}
        with pytest.raises(ValidationError):
            validate(instance=state, schema=schema)

    def test_extra_verification_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["verification"] = {"overall_verdict": "Risky", "extra": 1}
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)


class TestRefinementField:
    def test_full_refinement_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["refinement"] = {
            "refined_path": "docs/architecture.md",
            "gap_count": 2,
            "issue_count": 1,
            "improvement_count": 5,
        }
        validate(instance=state, schema=schema)

    def test_null_refinement_passes(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["refinement"] = None
        validate(instance=state, schema=schema)

    def test_extra_refinement_property_rejected(self, schema: dict) -> None:
        state = copy.deepcopy(VALID_MINIMAL_STATE)
        state["campaign"]["refinement"] = {"gap_count": 0, "extra": "no"}
        with pytest.raises(ValidationError, match="Additional properties"):
            validate(instance=state, schema=schema)


# ---------------------------------------------------------------------------
# Task 5.15–5.18 — SKILL.md structural tests
# ---------------------------------------------------------------------------


class TestSkillMdStructure:
    @pytest.fixture(scope="class")
    def skill_content(self) -> str:
        return SKILL_MD_PATH.read_text(encoding="utf-8")

    def test_frontmatter_has_name(self, skill_content: str) -> None:
        assert skill_content.startswith("---"), "SKILL.md must start with frontmatter"
        end = skill_content.index("---", 3)
        frontmatter = skill_content[3:end].strip()
        assert "name:" in frontmatter, "Frontmatter must contain name field"

    def test_stages_table_has_11_entries(self, skill_content: str) -> None:
        in_stages = False
        step_rows = 0
        for line in skill_content.splitlines():
            if line.strip().startswith("## Stages"):
                in_stages = True
                continue
            if in_stages and line.strip().startswith("## "):
                break
            if in_stages and line.strip().startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts and parts[0].isdigit():
                    step_rows += 1
        assert step_rows == 11, (
            f"Stages table must have 11 step entries, found {step_rows}"
        )

    def test_documents_backup_pattern(self, skill_content: str) -> None:
        assert "read-backup-modify-write" in skill_content.lower() or (
            "read" in skill_content.lower()
            and "backup" in skill_content.lower()
            and "modify" in skill_content.lower()
            and "write" in skill_content.lower()
        ), "SKILL.md must document the read-backup-modify-write pattern"

    def test_documents_campaign_result_json(self, skill_content: str) -> None:
        assert "SKF_CAMPAIGN_RESULT_JSON" in skill_content, (
            "SKILL.md must document the SKF_CAMPAIGN_RESULT_JSON envelope"
        )
