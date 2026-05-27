# Campaign Report — {{campaign_name}}

## Campaign Summary

| Field | Value |
|-------|-------|
| **Campaign** | {{campaign_name}} |
| **Started** | {{started_at}} |
| **Completed** | {{completed_at}} |
| **Duration** | {{duration}} |
| **Quality Gate (Hard)** | {{quality_gate_hard}} |
| **Quality Gate (Soft Target)** | {{quality_gate_soft_target}} |
| **Quality Gate (Soft Fallback)** | {{quality_gate_soft_fallback}} |
| **Skills Completed** | {{skills_completed}} |
| **Skills Failed** | {{skills_failed}} |
| **Skills Skipped** | {{skills_skipped}} |

## Skills Overview

| Name | Tier | Status | Quality Score | Pin | Workarounds |
|------|------|--------|---------------|-----|-------------|
{{skills_table}}

## Quality Scores

| Metric | Value |
|--------|-------|
| **Minimum** | {{quality_min}} |
| **Maximum** | {{quality_max}} |
| **Average** | {{quality_avg}} |

### Per-Skill Breakdown

{{quality_breakdown}}

## Findings Summary

- **Total workarounds applied:** {{total_workarounds}}
- **Skills with workarounds:** {{skills_with_workarounds}}
- **Doc-rot corrections:** tracked per-skill in health-check findings (not aggregated in campaign state)

## Workarounds Applied

{{workarounds_list}}

## Duration Breakdown

| Skill | Started | Completed | Duration |
|-------|---------|-----------|----------|
{{duration_table}}

## Failed / Skipped Skills

{{failed_skipped_section}}
