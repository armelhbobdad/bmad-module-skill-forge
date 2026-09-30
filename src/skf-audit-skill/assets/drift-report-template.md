---
workflowType: 'audit-skill'
stepsCompleted: []
lastStep: ''
date: ''
user_name: ''
skill_name: ''
skill_path: ''
source_path: ''
forge_tier: ''
# Run context, written as each value is known (init §6, re-index §5,
# structural-diff §6), so later steps read it from this file.
confidence_mode: ''
audited_version: ''
audited_version_reason: ''
manifest_version: ''
provenance_map: ''
provenance_generated_at: ''
provenance_age_days: ''
baseline_ref: ''
baseline_commit: ''
audit_ref: ''
audit_ref_source: ''
audit_commit: ''
latest_tag: ''
remote_head: ''
upstream_fetch: ''
ast_fallback_files: []
applied_transforms: []
drift_score: ''
nextWorkflow: ''
previousWorkflow: 'create-skill'
---

# Drift Report: {skill_name}

## Audit Summary

**Confidence Mode:** {confidence_mode}
**Skill:** {skill_name}
**Source:** {source_path}
**Tier:** {forge_tier}
**Date:** {date}
**Overall Drift Score:** {drift_score}

| Category  | Count |
|-----------|-------|
| CRITICAL  |       |
| HIGH      |       |
| MEDIUM    |       |
| LOW       |       |
| **Total** |       |

---

## Structural Drift

<!-- Appended by structural-diff, or for a compose-mode stack by constituent-freshness -->
<!-- Constituent Freshness (compose-mode stacks): drifted, missing and not-compared constituents; each drifted (HIGH) or missing (MEDIUM) one is a finding -->
<!-- Provenance label differences (not drift): informational table, rendered only when label_changes[] is non-empty and excluded from Total Drift Items -->

---

## Semantic Drift

<!-- Appended by semantic-diff (Deep tier only) -->

---

## Severity Classification

<!-- Appended by severity-classify -->

---

## Documentation Drift

<!-- Appended by step-doc-drift -->

---

## Remediation Suggestions

<!-- Appended by report -->

---

## Provenance

<!-- Appended by report -->
