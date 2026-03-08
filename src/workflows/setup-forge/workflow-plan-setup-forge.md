---
conversionFrom: 'src/workflows/setup-forge/setup-forge.spec.md'
originalFormat: 'Specification/Placeholder'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-remaining', 'step-10-confirmation']
created: 2026-02-26
status: CONFIRMED
confirmationDate: 2026-02-26
confirmationType: conversion
coverageStatus: complete
approvedDate: 2026-02-26
validationStatus: COMPLETE
validationDate: 2026-02-26
validationReport: validation-report.md
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/setup-forge/setup-forge.spec.md
**Original Format:** Specification/Placeholder (not yet implemented)
**Detected Structure:** 5-step create-only workflow spec with defined steps, inputs, outputs, and agent integration

---

## Original Workflow Analysis

### Goal (from source)

Initialize forge environment, detect tools, set tier, auto-index project

### Original Steps (Complete List)

**Step 1:** detect-tools - Check for gh, ast-grep, QMD availability
**Step 2:** determine-tier - Set Quick/Forge/Deep based on tools found
**Step 3:** create-config - Generate forge-config.yaml with tier and tool flags
**Step 4:** auto-index - Index current project as QMD collection (Deep only)
**Step 5:** report - Display forge status, tier, and capabilities

### Output / Deliverable

- `forge-config.yaml` — Tier and tool configuration
- `forge-data/` directory created
- `_bmad/_memory/forger-sidecar/forge-tier.yaml` — Capability flags
- `_bmad/_memory/forger-sidecar/preferences.yaml` — User preferences (defaults on first run)

### Input Requirements

**Required:**
- Project root path

**Optional:**
- `--update-spec` flag to fetch latest agentskills.io spec schema

### Key Instructions to LLM

- Ferris agent in Architect mode is the primary operator
- Tier-aware communication: acknowledge detected tier in responses
- Zero hallucination: tool detection must be empirical (actually run commands), not assumed
- Progressive capability: adapt behavior based on detected tier

---

## Conversion Notes

**What works well in original:**
- Clear 5-step decomposition with logical progression
- Well-defined progressive tier system (Quick/Forge/Deep)
- Three distinct output artifacts with clear purposes
- Correctly identified as foundation workflow all others depend on

**What needs improvement:**
- `--update-spec` is underspecified — deduced as convenience flag to fetch agentskills.io schema for downstream validation, not a core step
- No re-run behavior defined — deduced as re-detect and overwrite (config/tier), preserve (preferences), skip-if-exists (forge-data/), report changes
- Step 04 (auto-index) is conditional (Deep-only) — needs graceful skip logic
- Missing `preferences.yaml` creation with defaults on first run

**Compliance gaps identified:**
- No workflow.md entry point file
- No step files exist (steps-c/ directory not created)
- No BMAD frontmatter or step architecture
- No menu handling or continuation logic
- No state tracking via stepsCompleted
- No data/ or templates/ directories

**Deduced design decisions:**
- `--update-spec` handled as optional action within report step, not its own step
- Re-run behavior: re-detect tools, overwrite config/tier, preserve preferences, report tier changes
- `preferences.yaml` created with defaults if missing, never overwritten
- `forge-data/` directory creation is idempotent (skip if exists)

---

## Classification Decisions

**Workflow Name:** setup-forge
**Target Path:** `_bmad/skf/workflows/setup-forge/`

**4 Key Decisions:**
1. **Document Output:** false — action-based workflow producing config files as side effects, not a progressively-built document
2. **Module Affiliation:** SKF — core initializer for the Skill Forge module
3. **Session Type:** single-session — tool detection and config generation completes in under 5 minutes
4. **Lifecycle Support:** create-only — idempotent re-run replaces the need for edit/validate modes

**Structure Implications:**
- Simple `steps-c/` folder only, no edit/validate modes
- No `step-01b-continue.md` needed
- No document template — output is config files written directly
- Standard init step without continuation logic

---

## Advanced Elicitation Refinements

*Applied from 5-method analysis: Architecture Decision Records, Pre-mortem, First Principles, Critique and Refine, Red Team vs Blue Team*

### Config File Consolidation
- **forge-tier.yaml** (sidecar) is the single source of truth for tool availability and tier
- **forge-config.yaml** must have a distinct, non-overlapping purpose — module-level settings (output paths, skill defaults, module preferences) NOT tier/tool duplication
- If forge-config.yaml has no unique purpose beyond tier data, eliminate it and use forge-tier.yaml only

### Tool Verification Over Detection
- Step 01 must verify tools are functional, not just present
- Use `ast-grep --version`, `gh --version`, `qmd status` — not just `which` or `command -v`
- QMD specifically: check it's initialized, not just installed

### Preferences Enhancement
- Add `tier_override` field to preferences.yaml for manual tier forcing
- Allows users to force Deep when tools are partially available (e.g., QMD coming soon)
- Re-run respects override: if set, skip detection for that tier and use override

### Step 04 Resilience
- QMD auto-indexing could be slow on large projects
- Step 04 needs timeout awareness and graceful degradation
- If indexing fails/times out, forge-tier.yaml still records `qmd: true` — index can be re-attempted later

### Report Framing
- Frame capabilities positively: "Your Forge tier gives you AST-backed analysis and structural code search"
- Do NOT list what was skipped or missing — no "You're missing QMD for Deep tier"
- On re-run: report tier changes explicitly ("Upgraded from Quick to Forge — ast-grep now available")

### `--update-spec` Placement
- Owned by report step as optional post-action
- Not its own step — fires at end if flag is present
- Requires gh or web access to fetch latest agentskills.io schema

---

## Requirements

**Flow Structure:**
- Pattern: Linear with conditional branch (step 03 auto-index is Deep-only)
- Phases: Init → Detect & Verify + Determine Tier → Write Config → [Deep?] Auto-Index → Report
- Estimated steps: 4 step files (merged detect+tier into one, auto-index+report could merge but kept separate for conditional clarity)
- Revised step plan:
  - step-01: detect-and-tier — verify all 3 tools functional, calculate tier (or apply tier_override)
  - step-02: write-config — write forge-tier.yaml, create preferences.yaml defaults if missing, ensure forge-data/ exists
  - step-03: auto-index — QMD collection indexing of project (Deep tier only, skip gracefully for Quick/Forge, timeout resilient)
  - step-04: report — display forge status with positive capability framing, handle --update-spec if flagged, report tier changes on re-run

**User Interaction:**
- Style: Fully autonomous — zero user interaction during execution
- Decision points: None — all decisions are algorithmic (tool exists? → tier assignment)
- Checkpoint frequency: None — runs straight through, report at end

**Inputs Required:**
- Required: Project root path (implicit from BMAD context)
- Optional: `--update-spec` flag, `tier_override` in preferences.yaml
- Prerequisites: BMAD installed with SKF module active, Ferris agent available

**Output Specifications:**
- Type: Action-based (config file generation + directory creation + tool verification)
- Files created/updated:
  - `_bmad/_memory/forger-sidecar/forge-tier.yaml` — single source of truth for tools + tier + timestamp
  - `_bmad/_memory/forger-sidecar/preferences.yaml` — user defaults (create if missing, never overwrite)
  - `forge-data/` directory — created if missing, skipped if exists
- Eliminated: `forge-config.yaml` — consolidated into forge-tier.yaml to prevent drift
- Display: Forge status report with tier, capabilities, and positive framing
- Frequency: Single execution per run (idempotent, safe to re-run)

**Success Criteria:**
- All 3 tools (ast-grep, gh, qmd) verified via version/status commands, results accurately recorded
- Correct tier assigned from tool availability (or tier_override respected if set)
- forge-tier.yaml written with tools, tier, and tier_detected_at timestamp
- preferences.yaml exists with defaults (created on first run, preserved on re-run)
- forge-data/ directory exists
- Report displayed with positive capability framing (no "missing" language)
- On re-run: tier changes detected and reported (upgrade/downgrade/same)
- QMD auto-index completes or degrades gracefully on timeout (Deep tier only)

**Instruction Style:**
- Overall: Prescriptive — exact operations, no creative facilitation
- Notes: Each step has precise shell commands, file write operations, and conditional logic. No open-ended questions or user discovery needed. Tool verification uses specific commands (ast-grep --version, gh --version, qmd status), not existence checks.

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** Excluded — fully autonomous workflow, no creative exploration needed
- **Advanced Elicitation:** Excluded — no content to refine, purely mechanical operations
- **Brainstorming:** Excluded — no ideation needed in tool detection

**LLM Features:**
- **Web-Browsing:** Excluded — tool detection is local; --update-spec uses gh/curl via shell
- **File I/O:** Included — core to workflow (read/write forge-tier.yaml, preferences.yaml, create forge-data/)
- **Sub-Agents:** Excluded — simple linear flow, no parallel specialization
- **Sub-Processes:** Excluded — no parallel processing needed

**Memory:**
- Type: Single-session, no complex tracking
- Sidecar file: forge-tier.yaml serves as persistent state (read on re-run to detect tier changes)
- No stepsCompleted tracking needed (non-document, single-session)

**External Integrations:**
- **QMD MCP server:** Required for step-03 auto-index (Deep tier only) — must be manually installed by the user following official QMD documentation
- No other external integrations

**Installation Requirements:**
- **QMD MCP server:** Manual installation required for Deep tier — not bundled with BMAD, user follows official docs
- ast-grep and gh are standard CLI tools installed independently by the user

---

## Workflow Design

### File Structure

```
setup-forge/
├── workflow.md                    # Entry point
├── data/
│   └── tier-rules.md             # Tier calculation rules + capability descriptions
└── steps-c/
    ├── step-01-detect-and-tier.md
    ├── step-02-write-config.md
    ├── step-03-auto-index.md
    └── step-04-report.md
```

No templates/ directory (non-document workflow).

### Step Sequence

| Step | File | Type | Menu | Goal |
|------|------|------|------|------|
| 01 | step-01-detect-and-tier.md | Init (Non-Continuable) | Auto-proceed | Verify 3 tools functional, check tier_override, calculate tier, read previous tier |
| 02 | step-02-write-config.md | Middle (Simple) | Auto-proceed | Write forge-tier.yaml, create preferences.yaml defaults if missing, ensure forge-data/ exists |
| 03 | step-03-auto-index.md | Middle (Simple + Conditional) | Auto-proceed | QMD index project (Deep only), skip gracefully otherwise |
| 04 | step-04-report.md | Final Step | None | Display status with positive framing, handle --update-spec, report tier changes |

### Step Detail: step-01-detect-and-tier

**Frontmatter refs:** nextStepFile, tierRulesData (../data/tier-rules.md)
**Actions:**
1. Load tier-rules.md for tier calculation reference
2. Read existing forge-tier.yaml if present → store as {previous_tier}
3. Read existing preferences.yaml if present → check for tier_override
4. Run `ast-grep --version` → record result (available/unavailable + version)
5. Run `gh --version` → record result
6. Run `qmd status` → record result (check initialized, not just installed)
7. Calculate tier from tier-rules.md logic (or apply tier_override if set)
8. Store {detected_tools}, {calculated_tier}, {previous_tier} in context
9. Auto-proceed to step-02

**Error handling:** Tool command failures are NOT errors — they indicate tool unavailability. Record as unavailable and continue.

### Step Detail: step-02-write-config

**Frontmatter refs:** nextStepFile
**Actions:**
1. Write forge-tier.yaml with: tools (ast_grep, gh_cli, qmd booleans), tier, tier_detected_at timestamp
2. Check if preferences.yaml exists
   - If missing: create with defaults (tier_override: ~, plus any other default preferences)
   - If exists: preserve entirely, do not modify
3. Check if forge-data/ directory exists
   - If missing: create it
   - If exists: skip
4. Auto-proceed to step-03

**Error handling:** File write failure → report error clearly, halt workflow.

### Step Detail: step-03-auto-index

**Frontmatter refs:** nextStepFile
**Actions:**
1. Check {calculated_tier}
2. If Deep:
   - Run QMD collection indexing of current project
   - Handle timeout gracefully (if indexing exceeds reasonable time, log and continue)
   - If indexing fails: log that index needs retry, do NOT fail the workflow
3. If Quick or Forge:
   - Skip silently — no output, no "missing" messaging
4. Auto-proceed to step-04

**Error handling:** QMD failures degrade gracefully. forge-tier.yaml already records qmd: true — index can be retried later.

### Step Detail: step-04-report

**Frontmatter refs:** tierRulesData (../data/tier-rules.md)
**Actions:**
1. Load tier-rules.md for capability descriptions
2. Display forge status report:
   - Detected tier with positive capability framing (from tier-rules.md)
   - Tool availability summary (versions detected)
   - If re-run: report tier change (upgrade/downgrade/same) with what changed
3. If --update-spec flag present:
   - Fetch latest agentskills.io schema via gh/curl
   - Store in forge-data/
4. Final summary: "Forge ready. [Tier] tier active."

**Error handling:** --update-spec fetch failure → warn but don't fail.

### Data Flow

```
step-01 ──→ step-02 ──→ step-03 ──→ step-04
  │            │            │            │
  │reads:      │reads:      │reads:      │reads:
  │ tier-rules │ context    │ context    │ tier-rules
  │ forge-tier │            │            │ context
  │ prefs      │writes:     │writes:     │
  │            │ forge-tier │ QMD index  │displays:
  │sets:       │ prefs      │ (Deep)     │ report
  │ tools      │ forge-data/│            │
  │ tier       │            │            │fetches:
  │ prev_tier  │            │            │ spec (opt)
```

### Interaction Pattern
- All steps: Auto-proceed (Menu Pattern 3)
- Zero user interaction during execution
- Report step is display-only output

### Role and Persona
- Ferris agent, prescriptive system task execution
- Forge metaphor used briefly in final report only
- No collaborative dialogue, no questions asked

### Validation and Error Handling
- Tool command failures → not errors, record as unavailable
- File write failures → real errors, halt and report
- QMD index failures → degrade gracefully, log for retry
- Invalid tier_override → ignore, use detected tier, warn in report

### Special Features
- Conditional logic in step-03 (Deep-only indexing)
- Re-run detection via existing forge-tier.yaml comparison
- No input discovery (first workflow, no dependencies)
- Upstream of ALL other SKF workflows (produces forge-tier.yaml)

### Subprocess Optimization
- Not applicable — simple sequential operations, no parallel analysis needed

---

## Foundation Build Complete

**Created:**
- Folder structure at: `_bmad-output/bmb-creations/workflows/setup-forge/`
- `workflow.md` — entry point with auto-proceed architecture, SKF config loading
- `data/tier-rules.md` — tier calculation rules, capability descriptions, re-run messages
- `steps-c/` directory — ready for step files

**Configuration:**
- Workflow name: setup-forge
- Continuable: no
- Document output: no (non-document, action-based)
- Mode: create-only
- Output template: none (non-document workflow)

**Next Steps:**
- Step 8: Build step-01-detect-and-tier.md
- Step 9: Build remaining steps (02, 03, 04)

---

## Step 01 Build Complete

**Created:**
- steps-c/step-01-detect-and-tier.md

**Step Configuration:**
- Type: Init (Non-Continuable)
- Input Discovery: No
- Menu: Auto-proceed (Pattern 3)
- Next Step: step-02-write-config.md
- No step-01b needed (single-session)

**Supporting Files:**
- data/tier-rules.md (created in foundation step)

---

## Step 02 Build Complete

**Created:**
- steps-c/step-02-write-config.md

**Step Configuration:**
- Type: Middle (Simple)
- Menu: Auto-proceed (Pattern 3)
- Next Step: step-03-auto-index.md

---

## Step 03 Build Complete

**Created:**
- steps-c/step-03-auto-index.md

**Step Configuration:**
- Type: Middle (Simple + Conditional)
- Menu: Auto-proceed (Pattern 3)
- Conditional: Deep tier → QMD indexing, other tiers → silent skip
- Next Step: step-04-report.md

---

## Step 04 Build Complete

**Created:**
- steps-c/step-04-report.md

**Step Configuration:**
- Type: Final Step
- Menu: None (workflow ends)
- References: data/tier-rules.md for capability descriptions
