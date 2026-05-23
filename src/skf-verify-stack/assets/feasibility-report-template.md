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

<!-- Appended by integrations.
Consumers grep for the `## Integration Verdicts` heading to locate the pair table.
The table header is fixed and MUST be emitted exactly as shown below: -->

| lib_a | lib_b | verdict | rationale |
|-------|-------|---------|-----------|

---

## Recommendations

<!-- Appended by synthesize -->

---

## Evidence Sources

<!-- Appended by synthesize — cite each skill's SKILL.md path, metadata_schema_version,
     confidence_tier, stack manifest (if any), and architecture/PRD doc paths -->
