---
workflowType: 'test-skill'
skillName: ''
skillDir: ''
runId: ''
testMode: ''
forgeTier: ''
hardGate: ''
testResult: ''
score: ''
threshold: ''
analysisConfidence: ''
toolingStatus: ''
workspaceDrift: ''
health_check_dispatched: false
testDate: ''
stepsCompleted: []
nextWorkflow: ''
---

# Test Report: {{skillName}}

<!--
Each stage writes its section in place of the heading below that it owns and
the placeholder comment under that heading, so every heading occurs once.
Before the result files are written, report.md §4c checks that each heading
occurs exactly once and that no placeholder comment is left: a stage that
skipped its section stops the run there. Do not reorder or delete the
headings or their placeholder comments.

Heading / owning step:
  Test Summary        → detect-mode §2
  Coverage Analysis   → coverage-check §5
  Coherence Analysis  → coherence-check §6
  External Validation → external-validators §5
  (hard gate)         → step-hard-gate reads the gap ledger; it writes the
                        Completeness Score section only when it blocks the run
  Completeness Score  → score §6, or step-hard-gate §3 on a blocked run
  Gap Report          → report §4c, rendered from the gap ledger (with the
                        Discovery Quality subsection)
-->

## Test Summary

<!-- Populated by detect-mode §2 -->

## Coverage Analysis

<!-- Populated by coverage-check §5 -->

## Coherence Analysis

<!-- Populated by coherence-check §6 (naive or contextual variant) -->

## External Validation

<!-- Populated by external-validators §5 -->

## Completeness Score

<!-- Populated by score §6, or by step-hard-gate §3 when the hard gate blocks the run -->

## Gap Report

<!-- Populated by report §4c from the gap ledger (includes the Discovery Quality subsection) -->
