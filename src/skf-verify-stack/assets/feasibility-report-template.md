---
schemaVersion: "1.0"
reportType: feasibility
projectName: ""
projectSlug: ""
generatedAt: ""
generatedBy: skf-verify-stack
overallVerdict: "CONDITIONALLY_FEASIBLE"
coveragePercentage: 0
pairsVerified: 0
pairsPlausible: 0
pairsRisky: 0
pairsBlocked: 0
recommendationCount: 0
prdAvailable: false
# Producer-local bookkeeping (not part of the shared consumer contract):
workflowType: 'verify-stack'
architectureDoc: ''
prdDoc: ''
previousReport: ''
skillsAnalyzed: 0
coverageCovered: null
coverageMissing: null
coverageReplaced: null
stepsCompleted: []
requirementsPass: ''
requirementsFulfilled: null
requirementsPartial: null
requirementsNotAddressed: null
deltaImproved: null
deltaRegressed: null
deltaNew: null
deltaUnchanged: null
---

# Stack Feasibility Report: {projectName}

**Verification Date:** {generatedAt}
**Architecture Document:** {architectureDoc}
**PRD Document:** {prdDoc}
**Skills Analyzed:** {skillsAnalyzed}

> Schema contract: `{feasibilitySchemaRef}` (schemaVersion `1.0`). Consumers MUST halt on `schemaVersion` mismatch.

## Executive Summary

**Overall Verdict:** {FEASIBLE | CONDITIONALLY_FEASIBLE | NOT_FEASIBLE}

{1-2 sentence summary}

---

## Coverage Analysis

<!-- Appended by coverage -->

---

## Integration Verdicts

<!-- Filled in place by integrations: one row per pair goes under this header.
The report holds this table once: consumers read it and reject a second copy. -->

| lib_a | lib_b | verdict | rationale |
|-------|-------|---------|-----------|

---

## Recommendations

<!-- Appended by synthesize -->

---

## Evidence Sources

<!-- Filled in place by synthesize: one row per skill goes under this header (the
next run's delta reads its evidence_tier column), then the stack manifest (if any)
and the architecture and PRD document paths. -->

| skill | evidence_tier | confidence_tier | metadata_schema_version | skill_md |
|-------|---------------|-----------------|-------------------------|----------|
