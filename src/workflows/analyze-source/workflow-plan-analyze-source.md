---
conversionFrom: 'src/workflows/analyze-source/analyze-source.spec.md'
originalFormat: 'workflow-spec-placeholder'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-remaining-steps']
created: 2026-02-27
status: BUILD_COMPLETE
validationStatus: COMPLETE
validationDate: 2026-02-27
validationReport: './validation-report.md'
approvedDate: 2026-02-27
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/analyze-source/analyze-source.spec.md
**Original Format:** Workflow specification (placeholder — not yet built)
**Detected Structure:** Single spec document defining a create-only, 6-step workflow for brownfield source code analysis and skill decomposition

---

## Original Workflow Analysis

### Goal (from source)

Decomposition engine — discover what to skill, recommend stack skill. Analyzes a large repo or multi-service project to identify discrete skillable units. Maps exports, service boundaries, and integration points. Produces N recommended skill-brief.yaml files and optionally recommends a stack skill. Primary entry point for brownfield onboarding.

### Original Steps (Complete List)

**Step 1:** scan-project - Map project structure, detect service boundaries
**Step 2:** identify-units - Identify discrete skillable units (services, libraries, modules)
**Step 3:** map-exports - Count and categorize exports per unit
**Step 4:** detect-integrations - Find cross-unit integration points
**Step 5:** recommend - Present recommendations with rationale
**Step 6:** generate-briefs - Create skill-brief.yaml per confirmed unit

### Output / Deliverable

- N x `{forge_data_folder}/{unit-name}/skill-brief.yaml` — One per recommended unit
- Analysis summary report

### Input Requirements

**Required:**
- Project root or repo path

**Optional:**
- Scope hints (monorepo packages, service directories)

### Key Instructions to LLM

- Primary agent: Ferris (Architect mode)
- Workflow type: Feature — discovery and planning
- Create-only mode (steps-c/ only, no edit or validate modes)
- Installed path: {project-root}/_bmad/skf/workflows/analyze-source
- web_bundle: true

---

## Conversion Notes

**What works well in original:**
- Clear 6-step decomposition pipeline with logical progression (scan → identify → map → detect → recommend → generate)
- Well-defined input/output contract (repo path in, skill-brief.yaml files out)
- Spec identifies the right granularity for brownfield analysis
- Correct positioning as brownfield entry point — gateway workflow before brief-skill → create-skill pipeline

**What needs improvement:**
- Spec is a placeholder with no implementation — steps need full instruction content
- No collaborative interaction patterns defined (menus, user decision points)
- No data files, templates, or supporting resources specified
- Missing details on how "skillable units" are defined and bounded (what boundaries define a discrete unit?)
- No tier awareness — all other SKF workflows use tier-dependent tooling (Quick=text patterns, Forge=AST, Deep=AST+QMD)
- No forge_data_folder integration despite referencing it for output paths
- No stack skill detection — should flag potential co-integrated library candidates for create-stack-skill

**Compliance gaps identified:**
- No workflow.md entry point file
- No step files exist yet (steps-c/ folder needs creation)
- No frontmatter with BMAD-required fields on steps
- No menu handling or continuation patterns
- No data/ or templates/ resources
- No validation mode (spec marks as create-only, but validation could add value)

---

## Memory-Informed Discovery Notes

### Preserve
- 6-step linear pipeline matching proven architecture across all SKF workflows (quick-skill, brief-skill, create-stack-skill)
- Brownfield entry point positioning in the SKF lifecycle

### Address
- Define "skillable unit" detection heuristics (service boundaries, package boundaries, independent entry points)
- Add tier-aware scanning: Quick (file structure only), Forge (AST analysis), Deep (semantic analysis with QMD)
- Connect to SKF config infrastructure (forge_data_folder, skills_output_folder)
- SKF module config.yaml doesn't exist yet — workflow needs graceful handling or setup-forge prerequisite

### Add
- Interactive recommendation gate at step 05 — user confirms/rejects each unit before brief generation (matches Gate pattern from create-stack-skill and brief-skill)
- Output aligned to skill-brief.yaml schema (9 required fields: name, version, source_repo, language, scope, description, forge_tier, created, created_by)
- Scope type detection per unit (full-library / specific-modules / public-api)
- Existing skill detection — check forge_data_folder for already-created skills to avoid duplicates
- Stack skill candidate flagging for units with strong co-integration patterns

### Audience
- Ferris in Architect mode — prescriptive precision, zero-hallucination, file:line citation tracing
- Developers onboarding existing multi-service projects needing automated decomposition

---

## Classification Decisions

**Workflow Name:** analyze-source
**Target Path:** {project-root}/_bmad/skf/workflows/analyze-source/

**4 Key Decisions:**
1. **Document Output:** true — produces N x skill-brief.yaml files + analysis summary report
2. **Module Affiliation:** skf — core SKF workflow with access to forge_data_folder, skills_output_folder, forge_tier
3. **Session Type:** continuable — large repos will consume massive tokens during scanning/mapping; needs step-01b-continue.md and stepsCompleted tracking
4. **Lifecycle Support:** create-only — discovery workflow is one-shot per project; re-analysis creates fresh rather than editing stale results

**Structure Implications:**
- Needs steps-c/ directory only (no steps-e/ or steps-v/)
- Needs step-01-init.md with continuation detection logic
- Needs step-01b-continue.md for resuming interrupted analysis
- Needs stepsCompleted tracking in output document frontmatter
- Output uses free-form template with progressive append
- Data folder for unit detection heuristics and skill-brief schema reference

---

## Requirements

**Flow Structure:**
- Pattern: Linear with strategic user gate
- Phases: Discovery (steps 01-04), Decision (step 05), Generation (step 06)
- Estimated steps: 6 create steps + 1 continuation step (step-01b) = 7 step files
- Output pattern: Plan-then-Build — steps 01-05 build analysis report, step 06 consumes report to generate skill-brief.yaml files

**User Interaction:**
- Style: Mixed — mostly autonomous discovery with collaborative gates
- Decision points:
  - Step 05: Confirm/reject each recommended skillable unit
  - Step 05: Flag stack skill candidates for create-stack-skill
  - Step 06: Final confirmation before writing files
- Checkpoint frequency: Auto-proceed steps 01-04, full gate at step 05, summary at step 06

**Inputs Required:**
- Required: Project root or repo path
- Required: SKF module config (forge_data_folder, skills_output_folder, forge_tier)
- Required: forge-tier.yaml (determines Quick/Forge/Deep analysis depth)
- Optional: Scope hints (monorepo packages, service directories to focus on)
- Optional: Exclusion patterns (vendor dirs, test dirs, generated code to skip)
- Prerequisites: setup-forge workflow must have been run
- Init check: Scan forge_data_folder for existing skills to avoid duplicate recommendations

**Output Specifications:**
- Type: Multi-file document output
- Analysis summary report: Structured format (Project Overview, Units Found, Integration Map, Recommendations, Generation Results)
- Skill-brief.yaml files: Strict format per schema (9 required fields: name, version, source_repo, language, scope, description, forge_tier, created, created_by)
- Output locations: skill-brief.yaml → {forge_data_folder}/{unit-name}/skill-brief.yaml, summary → {output_folder}/analyze-source-report-{project_name}.md
- Frequency: N briefs per run (one per confirmed unit)

**Success Criteria:**
- Complete project scan — all service boundaries, packages, and entry points mapped
- Every identified unit classified with clear boundary definition (scope type: full-library / specific-modules / public-api)
- Integration points documented — cross-unit dependencies and co-import patterns captured
- Stack skill candidates flagged for create-stack-skill
- Existing skills detected — units with skills in forge_data_folder flagged as skip/update
- User confirmed all recommendations before generation
- Generated skill-brief.yaml files validate — all 9 fields present, name uniqueness enforced, scope has >= 1 include pattern
- Downstream ready — each brief consumable by brief-skill or create-skill pipeline

**Instruction Style:**
- Overall: Prescriptive with Ferris Architect mode
- Zero-hallucination — only report what's found in codebase
- File:line citation tracing — every claim backed by evidence
- Step 05 uses prescriptive presentation with collaborative discussion (user can ask "why?", Ferris explains with evidence)
- Positive capability framing throughout

---

## Workflow Design Preview

**Step count:** 5 create steps + 1 continuation step (step-01b) = 6 step files

**Phase 0 — Initialization (step-01-init / step-01b-continue)**
- Load SKF config, forge-tier.yaml, check existing skills
- Accept project root + optional scope hints
- Continuation detection and resume logic

**Phase 1 — Discovery (steps 02-04, autonomous)**
- Step 02: scan-project — Map project structure, detect service boundaries, package manifests
- Step 03: identify-units — Classify discrete skillable units, assign scope types
- Step 04: map-and-detect — Count/categorize exports per unit AND find cross-unit integration points, flag stack skill candidates

**Phase 2 — Decision (step 05, collaborative gate)**
- Step 05: recommend — Present findings with rationale, show conflicts, user confirms/rejects each unit

**Phase 3 — Generation (step 06, autonomous)**
- Step 06: generate-briefs — Create skill-brief.yaml per confirmed unit, write analysis summary, present final results

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** available at step-05 (recommend) — included as optional [P] menu for creative exploration during collaborative unit review
- **Advanced Elicitation:** included as optional [A] menu at Step 05 only — quality gate for challenging unit boundary decisions
- **Brainstorming:** excluded — no ideation needed in code analysis

**LLM Features:**
- **Web-Browsing:** excluded — workflow analyzes local source code, not external resources
- **File I/O:** included — core to every step (reads project files, writes skill-brief.yaml + summary report)
- **Sub-Agents:** excluded — sequential approach sufficient for v1
- **Sub-Processes:** excluded — brief generation is lightweight, parallelization not needed

**Memory:**
- Type: continuable
- Tracking: stepsCompleted array, lastStep, lastContinued in output frontmatter
- State document: analysis summary report serves as persistent state (no sidecar needed)
- Step state: discovered units list, integration map, existing skills, confirmed units — all accumulate in report sections

**External Integrations:**
- None — fully self-contained, local filesystem only

**Installation Requirements:**
- None — all tools are built-in

---

## Workflow Design

### Step Sequence

| Step | Name | Type | Menu | Goal |
|------|------|------|------|------|
| 01 | init | Init (Continuable) | Auto-proceed | Load config, check continuation, accept project path, check existing skills, create report |
| 01b | continue | Continuation | Auto-proceed | Read stepsCompleted from report, route to resume point |
| 02 | scan-project | Middle (Simple) | C-only | Map project structure, detect service boundaries, package manifests |
| 03 | identify-units | Middle (Simple) | C-only | Classify discrete skillable units with scope types |
| 04 | map-and-detect | Middle (Simple) | C-only | Map exports per unit, detect cross-unit integrations, flag stack candidates |
| 05 | recommend | Middle (Standard) | A/P/C | Present all findings with rationale, user confirms/rejects each unit |
| 06 | generate-briefs | Final | None | Generate skill-brief.yaml per confirmed unit, write summary, recommend next workflow |

### Data Flow

```
Step 01 → Creates analysis-report.md from template
Step 02 → Appends "## Project Scan" section
Step 03 → Appends "## Identified Units" section
Step 04 → Appends "## Export Map" + "## Integration Points" sections
Step 05 → Appends "## Recommendations" section (with user confirmations)
Step 06 → Reads report → generates N skill-brief.yaml → appends "## Generation Results"
```

### File Structure

```
analyze-source/
├── workflow.md
├── data/
│   ├── unit-detection-heuristics.md    # Rules for identifying skillable units
│   └── skill-brief-schema.md          # Schema for skill-brief.yaml (9 fields)
├── templates/
│   └── analysis-report-template.md    # Output document template
└── steps-c/
    ├── step-01-init.md
    ├── step-01b-continue.md
    ├── step-02-scan-project.md
    ├── step-03-identify-units.md
    ├── step-04-map-and-detect.md
    ├── step-05-recommend.md
    └── step-06-generate-briefs.md
```

### Subprocess Optimization

| Step | Pattern | What | Fallback |
|------|---------|------|----------|
| 02 | Pattern 1 (Grep/Regex) | Scan directory structure for manifests, entry points, service configs across entire project | Sequential file reads in main thread |
| 04 | Pattern 2 (Per-file analysis) | Per-unit export mapping and integration detection | Analyze units sequentially in main thread |

### Workflow Chaining

**Prerequisites:**
- setup-forge (required) — produces forge-tier.yaml

**Downstream recommendations (step 06):**
- brief-skill — for units needing detailed scoping refinement
- create-skill — for units where generated briefs are sufficient
- create-stack-skill — for flagged stack skill candidates

**Output contract:**
- `{forge_data_folder}/{unit-name}/skill-brief.yaml` — per confirmed unit
- `{output_folder}/analyze-source-report-{project_name}.md` — analysis summary
- Frontmatter: workflowType: 'analyze-source', nextWorkflow, stepsCompleted

### Error Handling

| Scenario | Response |
|----------|----------|
| Missing forge-tier.yaml | Hard halt — "Run setup-forge first" |
| No skillable units found | Advisory exit — document empty scan results |
| Unit analysis partially fails | Continue with warnings, document gaps |
| Existing skill conflicts | Flag in recommendations, suggest update-skill |
| Project path invalid | Hard halt — request valid path |

### Role and Persona

- Ferris in Architect mode — prescriptive precision
- Zero-hallucination — only report what's found in codebase
- File:line citation tracing for all claims
- Tier-aware analysis depth: Quick (file structure), Forge (AST), Deep (AST+QMD)

---

## Foundation Build Complete

**Created:**
- Folder structure at: `_bmad-output/bmb-creations/workflows/analyze-source/`
- `workflow.md` — entry point with SKF config loading, subprocess fallback rule, tier-aware analysis principle
- `templates/analysis-report-template.md` — structured output with frontmatter tracking (stepsCompleted, confirmed_units, stack_skill_candidates, existing_skills)
- `data/skill-brief-schema.md` — 9-field schema with validation rules and YAML template
- `data/unit-detection-heuristics.md` — detection signals (strong/moderate/weak), boundary classification, disqualification rules, stack skill candidate detection, tier-aware scanning depth

**Configuration:**
- Workflow name: analyze-source
- Continuable: yes
- Document output: yes — Structured report + Strict YAML
- Mode: create-only

**Next Steps:**
- Step 8: Build step-01-init (and step-01b-continue) ✅
- Step 9: Build remaining steps (02 through 06)

---

## Step 01 Build Complete

**Created:**
- steps-c/step-01-init.md — continuable init with forge-tier check, project path collection, existing skill scan, auto-proceed
- steps-c/step-01b-continue.md — continuation handler with progress summary and step routing

**Step Configuration:**
- Type: Continuable init (auto-proceed)
- Input Discovery: No (but checks forge-tier.yaml prerequisite and existing skills)
- Next Step: step-02-scan-project
- Menu: Auto-proceed (no A/P — init step)

**Key Implementation Details:**
- Hard halt if forge-tier.yaml missing (directs to setup-forge)
- Scans forge_data_folder for existing skill-brief.yaml files
- Populates report frontmatter with project_path, forge_tier, existing_skills
- step-01b reads stepsCompleted to determine resume point and presents progress summary

---

## Steps 02-06 Build Complete

**Created:**
- steps-c/step-02-scan-project.md — Middle (Simple), C-only menu. Subprocess Pattern 1 for directory structure scanning. Maps directory tree, workspace configs, package manifests, entry points, service configs. Detects service boundaries with confidence levels. Presents scan results for user confirmation.
- steps-c/step-03-identify-units.md — Middle (Simple), C-only menu. Applies detection heuristics to each boundary. Classifies boundary type (service/package/module/library) and scope type (full-library/specific-modules/public-api). Runs disqualification checks. Cross-references existing_skills. Detects primary language per unit.
- steps-c/step-04-map-and-detect.md — Middle (Simple), C-only menu. Subprocess Pattern 2 (per-unit analysis). Maps export surfaces with tier-appropriate depth. Builds import graph cross-reference matrix. Detects integration points with coupling strength. Flags stack skill candidates using 4 indicators.
- steps-c/step-05-recommend.md — Middle (Standard), A/P/C menu. Collaborative gate — the primary user decision point. Builds recommendation cards with evidence-based rationale and proposed brief fields. User confirms (Y), rejects (N), or modifies (M) each unit. Addresses stack skill candidates. Requires final confirmation before proceeding.
- steps-c/step-06-generate-briefs.md — Final step, no menu. Generates skill-brief.yaml per confirmed unit using schema. Validates all 9 required fields. Presents generation preview for user confirmation before writing. Recommends next workflow per unit (create-skill, brief-skill, create-stack-skill, update-skill). Marks workflow complete.

**Step Configuration Summary:**

| Step | Type | Menu | Key Feature |
|------|------|------|-------------|
| 02 | Middle (Simple) | C-only | Subprocess Pattern 1 for broad scanning |
| 03 | Middle (Simple) | C-only | Heuristic-based classification with disqualification |
| 04 | Middle (Simple) | C-only | Subprocess Pattern 2 for per-unit deep analysis |
| 05 | Middle (Standard) | A/P/C | Collaborative gate — user confirms each unit |
| 06 | Final | None | Schema-validated YAML generation with next workflow recommendations |

**Data Flow Verification:**
- Step 02 appends "## Project Scan" → Step 03 reads boundaries from it
- Step 03 appends "## Identified Units" → Step 04 reads qualifying units from it
- Step 04 appends "## Export Map" + "## Integration Points" → Step 05 reads all analysis data
- Step 05 appends "## Recommendations" + populates confirmed_units → Step 06 reads confirmed units
- Step 06 appends "## Generation Results" + writes skill-brief.yaml files → Workflow complete
