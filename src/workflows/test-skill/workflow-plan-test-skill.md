---
conversionFrom: 'src/workflows/test-skill/test-skill.spec.md'
originalFormat: 'BMAD Workflow Specification (placeholder)'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-all-steps']
created: 2026-02-26
status: VALIDATED
approvedDate: 2026-02-26
validationDate: 2026-02-26
validationStatus: PASS
validationReport: './validation-report.md'
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/test-skill/test-skill.spec.md
**Original Format:** BMAD Workflow Specification (placeholder — not yet implemented)
**Detected Structure:** Single specification document defining a 6-step create-only workflow

---

## Original Workflow Analysis

### Goal (from source)

Cognitive completeness verification — Verifies that a skill is complete enough to be useful to an AI agent. Supports two modes: naive (individual skill API surface coverage) and contextual (stack skill coherence validation). Produces a completeness score and gap report. Acts as a quality gate before export.

### Original Steps (Complete List)

**Step 1:** load-skill - Load skill and metadata
**Step 2:** detect-mode - Determine naive (individual) vs contextual (stack) testing mode
**Step 3:** coverage-check - Compare documented exports against source API surface
**Step 4:** coherence-check - Validate internal consistency (stack: references match SKILL.md)
**Step 5:** score - Calculate completeness score
**Step 6:** gap-report - Generate gap report with specific remediation suggestions

### Output / Deliverable

- Completeness score (pass/fail with percentage)
- Gap report with specific missing items and remediation suggestions

### Input Requirements

**Required:**
- Skill path (`{skills_output_folder}/{name}/`)

**Optional:**
- `--batch` flag with list of skills or directory
- Source path override

### Key Instructions to LLM

- Spec assigns **Ferris (Audit mode)** as the primary agent
- Create-only mode (steps-c/ only) — no edit or validate modal variants
- Document-producing workflow
- Must support `--batch` for testing multiple skills
- Quality gate role: determines if a skill is ready for export
- Two distinct analysis modes (naive vs contextual) require branching logic

---

## Conversion Notes

**What works well in original:**
- Clear step decomposition with well-defined goals
- Dual-mode architecture (naive/contextual) is well-scoped
- Input/output requirements are explicit
- Quality gate purpose is clear
- Correct lifecycle positioning: test-skill sits between create-skill and export-skill (Setup → Analyze → Brief → Create → **Test** → Export)
- Ferris Audit mode assignment is architecturally correct

**What needs improvement:**
- No step-level detail — only names and one-line goals exist
- No menu handling, user interaction points, or continuation flow defined
- No frontmatter configuration for steps
- No data files, templates, or output format specifications
- Batch mode mechanics are unspecified
- No forge tier awareness — coverage depth must scale with Quick/Forge/Forge+/Deep tiers
- No reference to forge-tier.yaml sidecar state for tier detection
- Zero hallucination principle not encoded — scoring must trace to AST citations

**Compliance gaps identified:**
- Missing: workflow.md entry point with proper frontmatter
- Missing: Step files with BMAD step-file architecture
- Missing: Frontmatter variables for configurable paths
- Missing: Menu handling and user interaction patterns
- Missing: State tracking via stepsCompleted
- Missing: Output document template/format specification
- Missing: Step processing rules and execution protocols

**Memory-informed design additions:**
- Tier-aware coverage: Quick=file/structure check, Forge=AST API surface, Deep=cross-repo coherence
- Batch mode: --batch with --continue for sidecar-checkpointed resume (matches create-skill pattern)
- Batch produces per-skill reports with optional consolidated summary
- Configurable pass/fail threshold (default overridable)
- Must read forge-tier.yaml from forger-sidecar to determine available analysis depth

---

## Classification Decisions

**Workflow Name:** test-skill
**Target Path:** {project-root}/_bmad/skf/workflows/test-skill

**4 Key Decisions:**
1. **Document Output:** true (completeness score + gap report)
2. **Module Affiliation:** SKF (Skill Forge)
3. **Session Type:** single-session
4. **Lifecycle Support:** create-only

**Structure Implications:**
- Only `steps-c/` folder needed (no steps-e/ or steps-v/)
- Standard init (no step-01b-continue.md needed)
- Free-form output template for test report document
- Access to SKF module variables (forge tier config, skills paths)
- Batch mode is a loop wrapper, not a multi-session concern

---

## Requirements

**Flow Structure:**
- Pattern: branching (by naive/contextual mode at step 02)
- Phases: Loading → Analysis → Scoring → Reporting
- Estimated steps: 6
- Branch point: Step 02 detect-mode determines naive vs contextual path
- Step 04 (coherence-check) is conditional — full execution in contextual mode, simplified/skipped in naive mode

**User Interaction:**
- Style: mostly autonomous (Ferris Audit mode — deterministic analysis)
- Decision points: none mid-flow; mode detection is automatic based on skill type
- Checkpoint frequency: entry (input validation) and exit (report delivery) only

**Inputs Required:**
- Required: skill path (`{skills_output_folder}/{name}/`), forge tier state (`forger-sidecar/forge-tier.yaml`)
- Optional: `--batch` flag with skill list or directory, `--continue` for interrupted batch resume, source path override, custom pass/fail threshold
- Prerequisites: setup-forge completed (tier detected), skill created via create-skill (SKILL.md exists)

**Output Specifications:**
- Type: document (structured test report)
- Format: structured (defined sections for machine-readability and batch comparison)
- Sections: Test Summary, Coverage Analysis, Coherence Analysis (contextual only), Completeness Score, Gap Report, Metadata
- Frequency: per-skill report; batch produces per-skill reports + optional consolidated summary

**Success Criteria:**
- Completeness score is accurate and traceable to code via AST citations (zero hallucination)
- Every gap has specific, actionable remediation suggestion
- Pass/fail threshold respected and clearly reported
- Naive mode correctly limits scope to API surface coverage
- Contextual mode validates cross-reference coherence for stack skills
- Batch mode produces consistent per-skill reports
- Report format parseable for downstream automation (export-skill can read it)

**Instruction Style:**
- Overall: prescriptive (audit/testing — exact procedures per check)
- Notes: Ferris Audit mode operates methodically; coverage check has specific comparison logic, coherence check has specific validation rules, scoring has defined formula

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** excluded — deterministic audit, no creative exploration
- **Advanced Elicitation:** excluded — no facilitative questioning needed
- **Brainstorming:** excluded — no idea generation in testing/scoring workflow

**LLM Features:**
- **Web-Browsing:** excluded — all analysis is local (source code + SKILL.md)
- **File I/O:** included — read SKILL.md, metadata.json, forge-tier.yaml, source files; write test report
- **Sub-Agents:** included — coverage-check and coherence-check as parallel sub-agents (batch efficiency)
- **Sub-Processes:** included — batch mode parallel skill testing

**Memory:**
- Type: single-session (no continuation tracking)
- Sidecar: read-only access to forge-tier.yaml for tier detection; batch checkpointing for --continue

**External Integrations:**
- **ast-grep:** required for Forge/Deep tier — AST-backed API surface comparison in coverage-check
- **QMD:** optional for Deep tier — cross-reference knowledge search for coherence enrichment
- **gh CLI:** optional for Deep tier — cross-repo reference verification

**Installation Requirements:**
- All external tools managed by forge tier system (setup-forge detects availability)
- No additional installation — test-skill gracefully degrades based on detected tier

**Structure Preview:**
- Phase 1: Initialization — validate skill path, read forge tier, load metadata
- Phase 2: Mode Detection — determine naive vs contextual based on skill type
- Phase 3: Analysis — coverage-check (all tiers) + coherence-check (contextual only), depth scales with tier
- Phase 4: Scoring & Reporting — calculate score, apply threshold, generate gap report, write test report

---

## Workflow Design

### Step Sequence

| # | Name | Type | Menu | Goal |
|---|------|------|------|------|
| 01 | init | Init with Input Discovery | Auto-proceed | Discover skill, load forge tier, validate inputs |
| 02 | detect-mode | Middle (Simple) | Auto-proceed | Determine naive vs contextual from skill metadata |
| 03 | coverage-check | Validation Sequence | Auto-proceed | Compare documented exports against source API surface |
| 04 | coherence-check | Validation Sequence (conditional) | Auto-proceed | Validate references/coherence (contextual=full, naive=simplified) |
| 04b | external-validators | Middle (Simple) | Auto-proceed | Run external validation tools (skill-check, tessl) and capture scores |
| 05 | score | Middle (Simple) | Auto-proceed | Calculate completeness score from findings |
| 06 | report | Final Step | C only | Generate gap report, finalize document, recommend next workflow |

### Interaction Flow

```
User provides skill path → [01] init (auto) → [02] detect-mode (auto) →
[03] coverage-check (auto) → [04] coherence-check (auto) →
[04b] external-validators (auto) → [05] score (auto) →
[06] report → [C] finalize
```

### Data Flow

- Step 01: loads SKILL.md, metadata.json, forge-tier.yaml → creates output from template
- Step 02: reads metadata type → sets {testMode} naive|contextual → appends Test Summary
- Step 03: reads SKILL.md exports + source files → subprocess AST analysis → appends Coverage Analysis
- Step 04: reads SKILL.md references → conditional depth by mode → appends Coherence Analysis
- Step 04b: runs skill-check and tessl against skill directory → captures external scores → appends External Validation
- Step 05: reads coverage + coherence + external validation findings → calculates score → appends Completeness Score
- Step 06: reads all findings → generates remediation per gap → appends Gap Report → finalizes

### Subprocess Optimization

| Step | Pattern | What | Returns |
|------|---------|------|---------|
| 03 | Pattern 2 (deep analysis) | Per-source-file AST export comparison | {file, exports_found, exports_documented, missing, extra} |
| 03 | Pattern 4 (parallel) | Batch mode: parallel per-skill testing | Per-skill coverage findings |
| 04 | Pattern 1 (grep/regex) | Grep skill files for references | {references_found, files_checked, broken_refs} |
| 04 | Pattern 2 (deep analysis) | Per-reference coherence validation | {ref, target_exists, type_matches, signature_matches} |

Fallback: All subprocesses have main-thread fallback.

### File Structure

```
test-skill/
├── workflow.md
├── data/
│   ├── scoring-rules.md
│   └── output-section-formats.md
├── steps-c/
│   ├── step-01-init.md
│   ├── step-02-detect-mode.md
│   ├── step-03-coverage-check.md
│   ├── step-04-coherence-check.md
│   ├── step-04b-external-validators.md
│   ├── step-05-score.md
│   └── step-06-report.md
└── templates/
    └── test-report-template.md
```

### Role & Persona

Ferris (Audit mode): methodical, precise, evidence-based. Zero hallucination — every finding cites AST evidence with file:line references. Tier-aware — states analysis depth in report. Non-judgmental — reports facts, suggests remediation.

### Workflow Chaining

- **Previous:** create-skill (required — SKILL.md must exist)
- **Next:** export-skill (if pass) or update-skill (if fail)
- **Input contract:** `{skills_output_folder}/{name}/SKILL.md` + `metadata.json` + `{sidecar_path}/forge-tier.yaml`
- **Output contract:** `{forge_data_folder}/{skill_name}/test-report-{skill_name}.md` with frontmatter: workflowType, testResult, score, nextWorkflow

### Output Template (Structured)

```markdown
---
workflowType: 'test-skill'
skillName: '{skill_name}'
testMode: '{naive|contextual}'
forgeTier: '{Quick|Forge|Forge+|Deep}'
testResult: '{pass|fail}'
score: '{N%}'
threshold: '{N%}'
testDate: '{date}'
nextWorkflow: '{export-skill|update-skill}'
---

# Test Report: {skill_name}

## Test Summary
## Coverage Analysis
## Coherence Analysis
## Completeness Score
## Gap Report
```
