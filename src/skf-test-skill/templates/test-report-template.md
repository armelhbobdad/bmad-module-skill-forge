---
workflowType: 'test-skill'
skillName: ''
skillDir: ''
runId: ''
testMode: ''
forgeTier: ''
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
Section order is LOAD-BEARING: step 5 §5 enforces it, step 6 §5 verifies
stepsCompleted against the canonical chain. Do not reorder or delete anchors.

Anchor / Step mapping:
  Test Summary       → detect-mode
  Coverage Analysis  → coverage-check
  Coherence Analysis → coherence-check
  External Validation→ external-validators
  (hard gate)        → step-hard-gate (reads findings, blocks or passes; no report section)
  Completeness Score → score
  Gap Report         → report (includes Discovery Quality subsection)
-->

## Test Summary

<!-- Populated by detect-mode §3 -->

## Coverage Analysis

<!-- Populated by coverage-check §5 -->

## Coherence Analysis

<!-- Populated by coherence-check §6 (naive or contextual variant) -->

## External Validation

<!-- Populated by external-validators §5 -->

## Completeness Score

<!-- Populated by score §6 -->

## Gap Report

<!-- Populated by report §3-§4b (includes Discovery Quality subsection) -->

