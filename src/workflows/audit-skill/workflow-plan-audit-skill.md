---
conversionFrom: 'src/workflows/audit-skill/audit-skill.spec.md'
originalFormat: 'BMAD Workflow Specification (Placeholder)'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-remaining-steps', 'step-10-confirmation']
created: 2026-02-27
status: VALIDATED
confirmationDate: 2026-02-27
confirmationType: conversion
coverageStatus: complete
validationStatus: COMPLETE
validationDate: 2026-02-27
validationReport: './validation-report.md'
approvedDate: 2026-02-27
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/audit-skill/audit-skill.spec.md
**Original Format:** BMAD Workflow Specification (Placeholder)
**Detected Structure:** 6-step create-only pipeline defined at spec level, no implementation files exist yet

---

## Original Workflow Analysis

### Goal (from source)

Drift detection between skill and current source. Compares an existing skill against its source code to detect drift. Forge tier: structural comparison via AST diff. Deep tier: full audit including semantic changes and temporal context via QMD. Produces a drift report with severity levels. ADR-A: core workflow, CI is optional export.

### Original Steps (Complete List)

**Step 1:** load-skill - Load existing skill and provenance map
**Step 2:** re-index - Re-scan source with current tools
**Step 3:** structural-diff - Compare AST extractions (Forge+)
**Step 4:** semantic-diff - Compare QMD knowledge context (Deep only)
**Step 5:** severity-classify - Classify drift items by severity
**Step 6:** report - Generate drift report

### Output / Deliverable

Drift report with severity levels (added/removed/changed exports, breaking changes). Document-producing workflow.

### Input Requirements

**Required:**
- Existing skill path
- Source code (current version)

**Optional:**
- None specified

### Key Instructions to LLM

- Primary agent: Ferris (Audit mode)
- Tiered operation: Forge tier (structural only) vs Deep tier (full semantic + QMD)
- The spec references AST diff for structural comparison and QMD for semantic context
- CI integration is noted as optional export (ADR-A decision)

---

## Conversion Notes (Memory-Enriched)

**What works well in original (preserve):**
- Clean 6-step pipeline with logical progression: load → scan → diff → classify → report
- Tiered Forge/Deep separation aligns with established SKF tier architecture
- Correct lifecycle positioning (Phase 2, after create-skill and test-skill)
- Clear input/output specification
- Document-producing output aligns with drift report use case

**What needs improvement (fix during build):**
- **Missing Quick tier path** — All SKF workflows support Quick/Forge/Deep with graceful degradation; Quick tier needs text-diff fallback
- **No provenance map format specification** — Step 01 loads it, but must reference known `provenance-map.json` from create-skill's `forge-data/{name}/` output
- **No confidence tier labels (T1/T2/T3)** — Every SKF workflow uses these for traceability; drift findings need confidence scoring
- **Step 04 conditional skip** — semantic-diff is Deep-only but spec has no skip logic or degradation behavior for Forge/Quick tiers
- No error handling or edge cases documented (missing skill, incompatible versions, no provenance map)
- No data files, templates, or supporting materials defined

**Missing features to add:**
- **Batch mode** (`--batch`, `--continue` flags) — Consistent with test-skill, create-skill, and all lifecycle workflows
- **Dual-mode support** — Individual skill vs stack skill auditing (stack skills have integration patterns needing cross-reference drift detection)
- **Remediation suggestions** — Like test-skill's gap report, drift items should include actionable fix recommendations
- **Update-skill chaining** — Drift report should optionally trigger update-skill workflow for detected issues

**Compliance gaps identified:**
- No step files exist (placeholder spec only)
- No workflow.md entry point
- No frontmatter on any files
- No data/ folder with supporting reference materials (severity classification rules, drift pattern definitions)
- No templates/ for drift report output format
- Mode is marked create-only — confirmed appropriate for audit (re-audit is a fresh run, not an edit)

**Cross-workflow integration points (from memory):**
- **Input from create-skill:** `forge-data/{name}/provenance-map.json`, `evidence-report.md`, `extraction-rules.yaml`
- **Input from setup-forge:** `forger-sidecar/forge-tier.yaml` for tier detection
- **Output feeds update-skill:** Drift report triggers remediation workflow
- **Sibling pattern: test-skill** — Same Ferris Audit mode, zero-hallucination AST citations, tier-aware depth scaling
- **SKF config:** Loads from `_bmad/skf/config.yaml` (project_name, output_folder, skills_output_folder, forge_data_folder, sidecar_path)

---

## Classification Decisions

**Workflow Name:** audit-skill
**Target Path:** {project-root}/_bmad/skf/workflows/audit-skill/

**4 Key Decisions:**
1. **Document Output:** true (drift report with severity levels)
2. **Module Affiliation:** SKF module
3. **Session Type:** single-session
4. **Lifecycle Support:** create-only

**Structure Implications:**
- Needs `steps-c/` folder only (no steps-e/ or steps-v/)
- Standard `step-01-init.md` (no continuation logic)
- Document template for progressive drift report building with `stepsCompleted` tracking
- SKF module variables available (forge_data_folder, skills_output_folder, sidecar_path)
- Config loaded from `_bmad/skf/config.yaml`
- Ferris Audit mode as primary agent with zero-hallucination AST citations

---

## Requirements

**Flow Structure:**
- Pattern: Linear with conditional skip (Step 04 skipped at Quick/Forge tier)
- Phases: Load & Baseline (01-02) → Analysis (03-04) → Assessment & Output (05-06)
- Estimated steps: 6 (matching spec)
- Step 01: init (load skill + provenance map + detect tier)
- Step 02: re-index (re-scan source with current tools)
- Step 03: structural-diff (AST comparison — Forge+ tiers)
- Step 04: semantic-diff (QMD comparison — Deep tier only, SKIP for Quick/Forge)
- Step 05: severity-classify (grade all drift items)
- Step 06: report (generate final drift report)

**User Interaction:**
- Style: Mostly autonomous with 1 confirmation gate
- Decision points: Gate 1 after Step 01 — confirm skill loaded, show baseline summary, offer degraded mode if provenance map missing
- Checkpoint frequency: Minimal — audit is deterministic analysis

**Inputs Required:**
- Required: Existing skill path (skills/{name}/ with SKILL.md, metadata.json)
- Required: Source code path (or auto-detect from provenance-map.json source_root)
- Prerequisites: setup-forge completed (forger-sidecar/forge-tier.yaml), skill created by create-skill (provenance-map.json in forge-data/{name}/)
- Optional: --batch flag for multiple skills, --continue for batch checkpoint resume, severity threshold filter

**Output Specifications:**
- Type: Document-producing drift report
- Format: Structured (required sections)
- Sections: Audit Summary, Structural Drift (Forge+), Semantic Drift (Deep only), Severity Classification (CRITICAL/HIGH/MEDIUM/LOW), Remediation Suggestions, Provenance
- Frequency: Single per skill (batch loops at workflow level)
- Output file: {forge_data_folder}/{skill_name}/drift-report-{timestamp}.md
- Pattern: Direct-to-Final (steps progressively build the report)

**Success Criteria:**
- All structural drift items detected with correct severity classification
- Every finding backed by AST file:line citations (zero hallucination)
- Confidence tier labels (T1/T2/T3) on all findings
- Graceful degradation: Quick (text diff) → Forge (AST diff) → Deep (AST + QMD)
- Actionable remediation suggestions per drift item
- Overall drift score: CLEAN / MINOR / SIGNIFICANT / CRITICAL

**Instruction Style:**
- Overall: Prescriptive
- Notes: Deterministic analysis, not creative facilitation. Matches established SKF pattern (test-skill, create-skill). Every step has exact instructions for what to load, compare, and output.

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** Excluded (menu option only) — Audit is deterministic analysis, not creative exploration
- **Advanced Elicitation:** Excluded (menu option only) — No phases benefit from deep elicitation
- **Brainstorming:** Excluded — Audit produces findings, not ideas

**LLM Features:**
- **File I/O:** Required — All phases read skill artifacts, source code, provenance maps; report step writes drift-report.md
- **Sub-Processes:** Included — Batch mode parallel auditing of multiple skills (Step 01 batch loop)
- **Sub-Agents:** Excluded — Single-agent workflow (Ferris Audit mode)
- **Web-Browsing:** Excluded — All analysis is local

**Memory:**
- Type: Single-session (no complex memory)
- Tracking: stepsCompleted in drift report frontmatter
- Sidecar: Reads forger-sidecar/forge-tier.yaml (pre-existing from setup-forge)

**External Integrations (SKF-specific, pre-detected by setup-forge):**
- **ast_bridge** (ast-grep): Required at Forge/Deep tier — Steps 02-03 structural extraction and comparison
- **gh_bridge** (gh CLI): Required at all tiers — Steps 01-02 source file reading
- **qmd_bridge** (QMD): Required at Deep tier only — Step 04 semantic knowledge context
- **skills_ref**: Included — Step 01 skill format validation and ecosystem cross-reference

**Installation Requirements:**
- None — all tools pre-detected by setup-forge workflow
- User preference: N/A (no installation needed)

---

## Workflow Design

### Step Sequence

| Step | Name | Type | Menu | Subprocess | Size Est. |
|------|------|------|------|------------|-----------|
| 01 | init | Init with Input Discovery | C only (user gate) | — | ~180 lines |
| 02 | re-index | Middle (Simple) | Auto-proceed | Pattern 2 (per-file AST) | ~150 lines |
| 03 | structural-diff | Middle (Simple) | Auto-proceed | Pattern 4 (parallel diff) | ~200 lines |
| 04 | semantic-diff | Middle (Simple) + Conditional Skip | Auto-proceed | Pattern 3 (QMD ops) | ~150 lines |
| 05 | severity-classify | Middle (Simple) | Auto-proceed | Pattern 3 (rules lookup) | ~180 lines |
| 06 | report | Final Step | No next step | — | ~200 lines |

### Step Details

**Step 01: init**
- Type: Init with Input Discovery
- Goal: Load existing skill, provenance map, and detect forge tier
- Input Discovery: skill path → SKILL.md + metadata.json, provenance-map.json from forge-data, forge-tier.yaml from sidecar
- Creates: drift report from template with frontmatter + Audit Summary skeleton
- User Gate: Present baseline summary (skill name, export count, provenance age, tier, source path). Offer degraded mode if provenance map missing.
- Menu: [C] Continue after confirmation
- Batch: If --batch, loop over skill list; if --continue, check sidecar checkpoint

**Step 02: re-index**
- Type: Middle (Simple), Auto-proceed
- Goal: Re-scan source code with current tier tools
- Quick: text pattern extraction via gh_bridge
- Forge: AST extraction via ast_bridge (T1 confidence)
- Deep: AST + QMD temporal context (T2 confidence)
- Subprocess: Pattern 2 — per source file, launch subprocess for extraction, return structured findings
- Output: Internal state (current extraction snapshot), no report append yet

**Step 03: structural-diff**
- Type: Middle (Simple), Auto-proceed
- Goal: Compare provenance map extractions against current scan
- Diff categories: added exports, removed exports, changed signatures
- Quick: text-based name comparison (T1-low)
- Forge/Deep: full AST structural comparison with line-level citations (T1)
- Subprocess: Pattern 4 — parallel comparison of export categories
- Output: Appends ## Structural Drift section to drift report

**Step 04: semantic-diff**
- Type: Middle (Simple) with Conditional Skip, Auto-proceed
- Goal: Compare QMD knowledge context (Deep tier only)
- If Deep → execute semantic comparison via qmd_bridge
- If Quick/Forge → skip with note in report
- Subprocess: Pattern 3 — QMD collection query for semantic changes
- Output: Appends ## Semantic Drift section (or skip notice) to report

**Step 05: severity-classify**
- Type: Middle (Simple), Auto-proceed
- Goal: Grade every drift finding by severity
- Loads: data/severity-rules.md for classification criteria
- CRITICAL: removed/renamed exports, changed signatures (breaking)
- HIGH: new public API not in skill
- MEDIUM: implementation changes behind stable API
- LOW: style/convention changes
- Subprocess: Pattern 3 — load rules, classify findings, return assignments
- Output: Appends ## Severity Classification section with categorized findings table

**Step 06: report**
- Type: Final Step (no nextStepFile)
- Goal: Finalize drift report with summary, remediation, provenance
- Calculate overall drift score: CLEAN / MINOR / SIGNIFICANT / CRITICAL
- Generate remediation suggestions per drift item
- Add update-skill chaining recommendation if CRITICAL/HIGH found
- Add provenance section (comparison metadata, tools used, timestamp)
- Update frontmatter: mark complete, set nextWorkflow if applicable

### Data Flow

```
Step 01 → Loads skill baseline + creates report skeleton
Step 02 → Produces current extraction snapshot (internal)
Step 03 → Appends ## Structural Drift (compares baseline vs current)
Step 04 → Appends ## Semantic Drift (Deep) or skip notice (Quick/Forge)
Step 05 → Appends ## Severity Classification (grades all findings)
Step 06 → Completes ## Audit Summary, ## Remediation, ## Provenance
```

### File Structure

```
audit-skill/
├── workflow.md                          # Entry point (Ferris Audit mode)
├── data/
│   ├── severity-rules.md                # CRITICAL/HIGH/MEDIUM/LOW classification rules
│   └── drift-report-template.md         # Structured report template with frontmatter
└── steps-c/
    ├── step-01-init.md                  # Init with input discovery + user gate
    ├── step-02-re-index.md              # Re-scan source (auto-proceed)
    ├── step-03-structural-diff.md       # AST comparison (auto-proceed)
    ├── step-04-semantic-diff.md         # QMD comparison/skip (auto-proceed)
    ├── step-05-severity-classify.md     # Grade findings (auto-proceed)
    └── step-06-report.md               # Final report generation
```

### Role and Persona

- Role: Skill auditor operating in Ferris Audit mode
- Communication: Structured evidence-based reporting with file:line citations
- Style: Prescriptive — every step has exact instructions
- Principle: Zero hallucination — every finding must trace to actual code

### Workflow Chaining

- Required from setup-forge: {sidecar_path}/forge-tier.yaml
- Required from create-skill: {forge_data_folder}/{skill_name}/provenance-map.json
- Output feeds: update-skill (if CRITICAL/HIGH drift found)
- Frontmatter contract: workflowType: 'audit-skill', nextWorkflow: 'update-skill'

### Error Handling

- Missing skill: Error with path guidance
- Missing provenance map: Offer degraded mode (text-diff, T1-low confidence)
- Missing forge-tier.yaml: Error — run setup-forge first
- No drift found: Report CLEAN status
- Step 04 at non-Deep tier: Graceful skip with documented reason
