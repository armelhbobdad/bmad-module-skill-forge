# Skill Kickoff — {{skill_name}}

## Campaign Context

- **Campaign:** {{campaign_name}}
- **Current Stage:** {{current_stage}}
- **Quality Gate:** {{quality_gate_summary}}

## Skill Identity

- **Skill:** {{skill_name}}
- **Tier:** {{skill_tier}}
- **Repository:** {{repo_url}}
- **Pin:** {{pin}}
- **Commit:** {{commit_sha}}

## Brief Summary

{{brief_summary}}

## Campaign Facts

{{persistent_facts}}

## Dependency State

{{dependency_status_table}}

## Standing Directive

{{directive_content}}

## Workarounds Applied

{{workarounds_list}}

## Pipeline Instructions

Execute the standard forge pipeline for **{{skill_name}}**:

1. **AN** (Analyze) — scope and source intelligence
2. **BS** (Brief Synthesis) — generate or validate the skill brief
3. **CS** (Compile Skill) — compile the SKILL.md artifact
4. **TS** (Test Skill) — run health-check validation

**Parameters:**
- Pin: {{pin}}
- Quality target: {{quality_gate_summary}}
