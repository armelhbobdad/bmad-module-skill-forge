---
conversionFrom: 'src/workflows/update-skill/update-skill.spec.md'
originalFormat: 'BMAD Workflow Specification (Placeholder)'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-remaining', 'validation']
created: 2026-02-27
status: VALIDATED
validationDate: 2026-02-27
validationReport: './validation-report.md'
approvedDate: 2026-02-27
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/update-skill/update-skill.spec.md
**Original Format:** BMAD Workflow Specification (Placeholder)
**Detected Structure:** Single spec file defining a 7-step create-only workflow for smart skill regeneration with [MANUAL] section preservation. No step files, templates, or data files exist yet — this is a design-phase placeholder.

---

## Original Workflow Analysis

### Goal (from source)

Smart regeneration preserving [MANUAL] sections. Detects changes in source code since last generation, re-extracts affected exports, diffs against existing provenance map, and regenerates SKILL.md while preserving any [MANUAL] sections the developer has added. Handles both individual and stack skills internally.

### Original Steps (Complete List)

**Step 1:** load-existing - Load existing skill and provenance map
**Step 2:** detect-changes - Diff source against provenance map
**Step 3:** re-extract - AST extraction on changed files only
**Step 4:** merge - Merge new extractions, preserve [MANUAL] sections
**Step 5:** validate - Validate updated skill against spec
**Step 6:** write - Write updated SKILL.md and provenance map
**Step 7:** report - Display change summary

### Output / Deliverable

Document-producing workflow that outputs:
- Updated `{skills_output_folder}/{name}/SKILL.md`
- Updated `{forge_data_folder}/{name}/provenance-map.json`
- Updated `{forge_data_folder}/{name}/evidence-report.md`

### Input Requirements

**Required:**
- Existing skill path (`{skills_output_folder}/{name}/`)
- Updated source code

**Optional:**
- None

### Key Instructions to LLM

- Primary agent: Ferris (Surgeon mode) — precision-focused, surgical changes only
- Workflow type: Core (part of the SKF module's essential functionality)
- Create-only mode (steps-c/ only, no tri-modal)
- Must handle both individual and stack skills internally (no separate workflows)
- Must preserve [MANUAL] sections — developer-authored content must survive regeneration
- Uses provenance map for change detection (diff-based, not full re-extraction)
- Build priority: Phase 2 (Lifecycle)

---

## Conversion Notes

**What works well in original:**
- Clear 7-step pipeline with well-defined responsibilities per step
- Provenance-map-driven change detection (efficient, targeted)
- Explicit [MANUAL] section preservation requirement
- Unified handling of individual and stack skills
- Well-defined input/output contract

**What needs improvement:**
- Spec is a placeholder — no implementation details exist for any step
- No data files, templates, or step files have been created
- No description of how [MANUAL] sections are identified or preserved
- No detail on AST extraction approach for re-extraction
- No error handling or edge case coverage (e.g., deleted exports, renamed files)

**Compliance gaps identified:**
- No step files exist (need full step-file architecture)
- No frontmatter standards applied yet
- No menu/continuation patterns defined
- No state tracking or stepsCompleted patterns
- No data files or templates referenced
- Installed path uses `{project-root}/_bmad/skf/workflows/update-skill` but needs proper BMAD structure

---

## Memory-Informed Conversion Notes

### Patterns from Prior Workflow Builds

**Tier-awareness (from create-skill, audit-skill, create-stack-skill):**
- Quick tier: text pattern matching, T1-low confidence
- Forge tier: AST structural extraction, T1 confidence
- Deep tier: AST + QMD semantic enrichment, T2 confidence
- Update-skill must implement tier-aware re-extraction matching these patterns

**Workflow chaining (from audit-skill #334):**
- Requires: setup-forge output (forge-tier.yaml), create-skill output (provenance-map.json + SKILL.md)
- Triggered by: audit-skill when CRITICAL/HIGH drift detected
- Produces: updated provenance-map.json feeding back into audit-skill cycle

**Ferris Surgeon mode (from agent plan #37):**
- Defined as "precise edits that preserve manual changes" — exact match for update-skill's purpose
- Zero-hallucination principle: every regenerated instruction must trace to code with AST file:line citations
- Confidence tier labeling (T1/T1-low/T2) required on all re-extracted content

**Subprocess patterns (from audit-skill #321):**
- Pattern 2: per-file AST extraction (for re-extract step)
- Pattern 4: parallel comparison (for detect-changes step)
- Pattern 3: QMD/rules operations (for Deep tier enrichment)

**Stack skill support (from create-stack-skill #297):**
- Must handle multi-file outputs: SKILL.md, references/*.md, integrations/*.md
- Stack skills use integration-first architecture with cross-cutting patterns
- Update must preserve [MANUAL] sections across ALL output files, not just SKILL.md

**Batch mode (from create-skill #89):**
- --batch flag for updating multiple skills
- --continue flag for checkpoint resume from sidecar

### Missing Features to Add During Conversion

1. Tier-aware re-extraction (Quick/Forge/Forge+/Deep graceful degradation)
2. Degraded mode for missing provenance map (fallback to full re-extraction)
3. Stack skill multi-file update support
4. Batch mode with checkpoint resume
5. Change summary with before/after diff visualization
6. Edge case handling: deleted exports, renamed files, moved functions
7. [MANUAL] section conflict resolution when regenerated content overlaps

---

## Classification Decisions

**Workflow Name:** update-skill
**Target Path:** {project-root}/_bmad/skf/workflows/update-skill/

**4 Key Decisions:**
1. **Document Output:** false (modifies existing files, does not produce new documents)
2. **Module Affiliation:** SKF (Phase 2 Lifecycle workflow, Ferris agent menu [US] Update Skill)
3. **Session Type:** single-session (targeted re-extraction on changed files only, efficient provenance-driven diffing)
4. **Lifecycle Support:** create-only (steps-c/ only — update-skill IS the edit operation for skill artifacts)

**Structure Implications:**
- Needs steps-c/ folder only (no steps-e/ or steps-v/)
- Standard step-01-init.md without continuation logic
- No stepsCompleted tracking in output (non-document)
- SKF module variables available: skills_output_folder, forge_data_folder, forge_tier, etc.
- Stored in SKF module's workflows directory alongside create-skill, audit-skill, etc.

---

## Requirements

**Flow Structure:**
- Pattern: linear
- Phases: load → diff → extract → merge → validate → write → report
- Estimated steps: 7 (matching spec pipeline)

**User Interaction:**
- Style: mostly autonomous with strategic gates
- Decision points: Gate 1 after load (confirm change scope), Gate 2 after merge (approve [MANUAL] conflict resolution if any)
- Checkpoint frequency: 2 gates — steps 02-03 and 05-07 auto-proceed

**Inputs Required:**
- Required: existing skill path ({skills_output_folder}/{name}/), sidecar/forge-tier.yaml (tier detection), {forge_data_folder}/{name}/provenance-map.json (export mappings + timestamps), existing SKILL.md + metadata.json
- Optional: --batch flag for multi-skill update, --continue flag for checkpoint resume, specific file list to restrict re-extraction scope
- Prerequisites: setup-forge completed (forge-tier.yaml), create-skill completed (provenance-map.json + SKILL.md exist)

**Output Specifications:**
- Type: action (modifies existing files in-place)
- Format: N/A (non-document)
- Actions: surgically updates SKILL.md, provenance-map.json, evidence-report.md; for stack skills also updates references/*.md and references/integrations/*.md
- Frequency: single skill per run (batch mode wraps multiple runs)

**Success Criteria:**
- All changed exports re-extracted with correct confidence tiers (T1/T1-low/T2)
- All [MANUAL] sections preserved intact with zero content loss
- Provenance map updated with new timestamps and file mappings
- No hallucinated content — every instruction traces to AST file:line citation
- Stack skills: all affected reference files updated consistently
- Evidence report reflects update operation with before/after provenance

**Instruction Style:**
- Overall: prescriptive
- Notes: matches established SKF pattern (setup-forge, create-skill, audit-skill all use prescriptive). Zero-hallucination principle requires exact AST citations. No room for creative interpretation when modifying existing skill artifacts.

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** excluded — deterministic surgical operation, no creative brainstorming applicable
- **Advanced Elicitation:** excluded — prescriptive workflow with no ambiguity points
- **Brainstorming:** excluded — not applicable to code-driven extraction pipeline

**LLM Features:**
- **Web-Browsing:** excluded — all data is local (source code + skill artifacts)
- **File I/O:** included — core requirement. Reads skill artifacts, provenance maps, source code. Writes updated SKILL.md, provenance-map.json, evidence-report.md, and stack reference files
- **Sub-Agents:** excluded — single-agent workflow (Ferris Surgeon mode)
- **Sub-Processes:** included — Pattern 2 (per-file AST extraction in Step 03), Pattern 4 (parallel diff comparison in Step 02)

**Memory:**
- Type: single-session (no continuation logic)
- Sidecar: reads forge-tier.yaml (pre-existing from setup-forge), reads/writes provenance-map.json

**External Integrations:**
- **ast_bridge:** required for Forge/Deep tier AST extraction (pre-detected by setup-forge)
- **gh_bridge:** required for all tiers to read source files
- **qmd_bridge:** required for Deep tier semantic enrichment only
- **skill-check:** required for validation against agentskills.io spec (Step 05) — `npx skill-check check --fix --format json` for validation + auto-fix + quality scoring, `diff` for before/after comparison, security scan for prompt injection detection, `split-body` for oversized body remediation

**Installation Requirements:**
- None — all tools pre-detected by setup-forge workflow
- User preference: N/A (no additional installs needed)

---

## Workflow Design

### Step Sequence

| Step | Name | Type | Goal | Menu | Size Est |
|------|------|------|------|------|----------|
| 01 | init | Init (Input Discovery) | Load existing skill, provenance map, forge tier; detect skill type; present baseline + change scope | [C] Continue | ~200 |
| 02 | detect-changes | Middle (Simple) | Diff source timestamps/hashes against provenance map; classify changes | Auto-proceed | ~180 |
| 03 | re-extract | Middle (Simple) | Tier-aware AST extraction on changed files only | Auto-proceed | ~200 |
| 04 | merge | Middle (Conditional) | Merge new extractions into existing skill; preserve [MANUAL] sections; conflict resolution | Conditional: [C] if conflicts, auto-proceed if clean | ~250 |
| 05 | validate | Validation Sequence | Validate updated skill against spec; verify [MANUAL] integrity; check confidence tiers | Auto-proceed | ~180 |
| 06 | write | Middle (Simple) | Write updated SKILL.md, provenance-map.json, evidence-report.md, stack reference files | Auto-proceed | ~180 |
| 07 | report | Final Step | Display change summary with diff, [MANUAL] preservation count, chaining recommendations | No next step | ~150 |

### Interaction Patterns

- **Step 01:** Menu Pattern 2 (C only) — user confirms scope after baseline summary
- **Steps 02-03:** Menu Pattern 3 (Auto-proceed) — deterministic operations
- **Step 04:** Conditional — [C] if [MANUAL] conflicts, auto-proceed if clean merge
- **Steps 05-06:** Menu Pattern 3 (Auto-proceed) — validation and write
- **Step 07:** Final Step — no menu, display summary and chaining recommendations
- **No A/P anywhere** — prescriptive surgical workflow

### Data Flow

```
Step 01 (init)
  IN:  skill path (user), forge-tier.yaml (sidecar), SKILL.md, metadata.json, provenance-map.json
  OUT: loaded baseline state → Step 02

Step 02 (detect-changes)
  IN:  provenance-map.json entries, source file timestamps/hashes
  OUT: change manifest (changed/added/deleted/moved files + export-level changes)

Step 03 (re-extract)
  IN:  change manifest, source files (changed only)
  OUT: fresh extractions with confidence tiers (T1/T1-low/T2)

Step 04 (merge)
  IN:  fresh extractions, existing SKILL.md content, [MANUAL] section markers
  OUT: merged SKILL.md content with [MANUAL] sections preserved

Step 05 (validate)
  IN:  merged content, agentskills.io spec (via `npx skill-check check --fix --format json`)
  OUT: validation results (pass/fail with quality score, diff comparison, security findings)

Step 06 (write)
  IN:  validated merged content, updated provenance data
  OUT: written files (SKILL.md, provenance-map.json, evidence-report.md, stack refs)

Step 07 (report)
  IN:  change manifest, merge results, validation results
  OUT: change summary displayed to user + chaining recommendation
```

### File Structure

```
update-skill/
├── workflow.md
├── data/
│   ├── manual-section-rules.md
│   └── merge-conflict-rules.md
└── steps-c/
    ├── step-01-init.md
    ├── step-02-detect-changes.md
    ├── step-03-re-extract.md
    ├── step-04-merge.md
    ├── step-05-validate.md
    ├── step-06-write.md
    └── step-07-report.md
```

### Role and Persona

- **Role:** Ferris in Surgeon mode — precision-focused, surgical changes only
- **Communication:** Terse, technical, confidence-labeled. Every statement backed by AST citations
- **Tone:** Clinical precision
- **Style:** Prescriptive throughout — zero ambiguity, zero hallucination

### Error Handling

- Missing SKILL.md → abort: "Run create-skill first"
- Missing provenance-map.json → offer degraded mode (full re-extraction, T1-low confidence)
- Missing forge-tier.yaml → abort: "Run setup-forge first"
- No changes detected → skip to Step 07: "No drift detected. Skill is current."
- [MANUAL] conflict → halt, present conflict details, require user resolution
- Deleted exports with [MANUAL] annotations → flag WARNING, require user decision
- Validation failure → present issues, recommend fixes, allow proceed or abort

### Subprocess Optimization

| Step | Pattern | What | Returns |
|------|---------|------|---------|
| 02 | Pattern 4 (Parallel) | Parallel timestamp/hash comparison across file categories | Change manifest per category |
| 03 | Pattern 2 (Per-file) | Per-file AST extraction on each changed file | Structured extraction findings per file |
| 03 (Deep) | Pattern 3 (Data Ops) | QMD query for semantic enrichment on changed exports | T2 evidence per export |
| 05 | Pattern 4 (Parallel) | Parallel validation checks (spec, [MANUAL] integrity, confidence tiers) | Structured validation results |

Fallback: All operations executable in main thread if subprocesses unavailable.

### Workflow Chaining

**Input Contract (Required):**
- setup-forge → sidecar/forge-tier.yaml
- create-skill or create-stack-skill → {skills_output_folder}/{name}/SKILL.md + {forge_data_folder}/{name}/provenance-map.json

**Input Contract (Optional):**
- audit-skill → drift report (when triggered by CRITICAL/HIGH drift)

**Output Contract:**
- Updated provenance-map.json → feeds back into audit-skill cycle
- Updated SKILL.md → consumed by export-skill, test-skill

**Step 07 Recommendation:**
- Validation passed: "Skill updated. Run audit-skill to verify, or export-skill to package."
- Issues remain: "Partial update. Run audit-skill to identify remaining drift."

---

## Foundation Build Complete

**Created:**
- Folder structure at: _bmad-output/bmb-creations/workflows/update-skill/
- workflow.md (entry point with SKF module config loading)
- data/manual-section-rules.md ([MANUAL] section detection, preservation, conflict types)
- data/merge-conflict-rules.md (5 change categories, merge priority order, stack skill rules)

**Configuration:**
- Workflow name: update-skill
- Continuable: no (single-session)
- Document output: no (action-based, modifies existing files)
- Mode: create-only (steps-c/)
- No output template needed (non-document workflow)

**Next Steps:**
- Step 8: Build step-01-init.md
- Step 9: Build remaining steps 02-07 (repeatable)

---

## Step 01 Build Complete

**Created:**
- steps-c/step-01-init.md (~150 lines)

**Step Configuration:**
- Type: non-continuable (no step-01b needed)
- Input Discovery: yes (discovers skill path, provenance map, forge-tier.yaml, [MANUAL] sections)
- Menu: Pattern 2 (C only) — user confirms baseline scope
- Next Step: step-02-detect-changes

**Supporting Files:**
- data/manual-section-rules.md (referenced from step-01 for [MANUAL] inventory)
- data/merge-conflict-rules.md (pre-created, used in step-04)

**Key Features:**
- Validates all required artifacts before proceeding (SKILL.md, metadata.json, forge-tier.yaml)
- Degraded mode option when provenance map missing
- Detects individual vs stack skill type from metadata.json
- Inventories all [MANUAL] sections across all output files (including stack references)
- Presents baseline summary table with forge tier, provenance age, export count, [MANUAL] count

---

## Steps 02-07 Build Complete

### Step 02: detect-changes (~180 lines)
- Type: Middle (Simple), Auto-proceed
- Pattern 4 parallel subprocess for timestamp/hash comparison
- 3-category scan: file-level changes, export-level changes, rename detection
- Change manifest output with per-file classification (MODIFIED/ADDED/DELETED/MOVED/RENAMED)
- No-change shortcut: skips directly to step-07-report if source matches provenance
- Next: step-03-re-extract

### Step 03: re-extract (~190 lines)
- Type: Middle (Simple), Auto-proceed
- Pattern 2 per-file subprocess for AST extraction on changed files only
- Tier-aware: Quick (regex, T1-low), Forge (AST, T1), Deep (AST+QMD, T1+T2)
- "DO NOT BE LAZY" directive ensures per-file subprocess extraction
- Conditional QMD enrichment (Pattern 3) for Deep tier only
- Next: step-04-merge

### Step 04: merge (~230 lines)
- Type: Middle (Conditional), [C] if conflicts / auto-proceed if clean
- Loads manual-section-rules.md and merge-conflict-rules.md
- 5-priority merge order: delete → move → rename → modify → add
- [MANUAL] block extraction, mapping, and preservation algorithm
- Conflict resolution UI: [K]eep / [R]emove / [E]dit per conflict
- Stack skill conditional merge across reference files
- Next: step-05-validate

### Step 05: validate (~190 lines)
- Type: Validation Sequence, Auto-proceed (advisory, non-blocking)
- Pattern 4 parallel validation across 4 checks:
  - Check A: Spec compliance (agentskills.io via skill-check)
  - Check B: [MANUAL] section integrity (byte-level comparison)
  - Check C: Confidence tier consistency (tier vs forge capabilities)
  - Check D: Provenance completeness (export-to-source mapping)
- Stack skill reference file validation conditional
- Next: step-06-write

### Step 06: write (~200 lines)
- Type: Middle (Simple), Auto-proceed
- Atomic file writes: SKILL.md, metadata.json (version increment), provenance-map.json (updated mappings), evidence-report.md (appended operation record)
- Stack skill reference file writes conditional
- Read-back verification for all written files
- Write verification table displayed before proceeding
- Next: step-07-report

### Step 07: report (~200 lines)
- Type: Final Step, no next step
- Handles no-change shortcut from step 02
- Comprehensive summary: operation metrics, change categories, export changes, confidence tier breakdown, [MANUAL] preservation status
- Validation findings presented if any
- Files written listed with paths
- Workflow chaining recommendations based on validation results
- Workflow ends here
