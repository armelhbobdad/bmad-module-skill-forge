---
conversionFrom: 'src/workflows/create-stack-skill/create-stack-skill.spec.md'
originalFormat: 'spec-placeholder'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-next-step', 'step-10-confirmation']
created: 2026-02-27
status: VALIDATED
approvedDate: 2026-02-27
confirmationDate: 2026-02-27
confirmationType: conversion
coverageStatus: complete
validationStatus: COMPLETE
validationDate: 2026-02-27
validationReport: validation-report.md
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/create-stack-skill/create-stack-skill.spec.md
**Original Format:** Specification placeholder (spec.md) — not a running workflow, a design blueprint
**Detected Structure:** Single specification document defining a 9-step create-only workflow for generating consolidated stack skills with integration patterns

---

## Original Workflow Analysis

### Goal (from source)

Consolidated project stack skill with integration patterns. Analyzes a project's dependency manifests, detects significant libraries, discovers co-import integration points, and produces a consolidated stack skill. The stack SKILL.md focuses on integration patterns — how libraries connect in THIS specific codebase. References/ contain per-library subsets and integration pair documentation. Absorbs analyze-stack internally.

### Original Steps (Complete List)

**Step 01:** detect-manifests - Find and parse dependency files (package.json, requirements.txt, Cargo.toml, etc.)
**Step 02:** rank-dependencies - Rank libraries by import frequency, present ranked list for user confirmation
**Step 03:** scope-confirmation - User confirms which dependencies to include in the stack skill
**Step 04:** parallel-extract - Extract per-library documentation in parallel (uses max_parallel_generation)
**Step 05:** detect-integrations - Find co-import patterns and integration points between libraries
**Step 06:** compile-stack - Assemble the main stack SKILL.md with integration layer
**Step 07:** generate-references - Write per-library reference files and integration pair documentation
**Step 08:** validate - Validate output against specification
**Step 09:** report - Display stack summary with integration graph

### Output / Deliverable

Multi-file document-producing workflow:
- `{skills_output_folder}/{project}-stack/SKILL.md` — Main skill: integration patterns + conventions
- `{skills_output_folder}/{project}-stack/context-snippet.md` — Compressed stack index for context loading
- `{skills_output_folder}/{project}-stack/metadata.json` — Metadata with `skill_type: "stack"`
- `{skills_output_folder}/{project}-stack/references/{library}.md` — Per-library reference subsets
- `{skills_output_folder}/{project}-stack/references/integrations/{pair}.md` — Cross-library integration patterns

### Input Requirements

**Required:**
- Project root with dependency manifests

**Optional:**
- Explicit dependency list (skip auto-detection)
- Scope overrides per library

### Key Instructions to LLM

- Uses `manifest_reader` for dependency detection
- ADR-D: compositional architecture — modular, composable design
- ADR-E: smart scope with developer confirmation — auto-detect then confirm with user
- Primary agent: Ferris (Architect mode)
- Step 04 uses `max_parallel_generation` for parallel extraction
- Create-only mode (steps-c/ only)

---

## Conversion Notes

**What works well in original:**
- Clear 9-step pipeline with logical progression (detect → rank → confirm → extract → analyze → compile → write → validate → report)
- Smart scope approach: auto-detect then user confirms
- Multi-file output structure with clear separation (main skill, context snippet, metadata, references)
- Integration-focused architecture — not just listing libraries but mapping how they connect
- Parallel extraction capability for performance

**What needs improvement:**
- Spec is a placeholder — no actual step file implementations exist
- No collaborative conversation patterns defined
- No menu handling or user interaction points specified beyond step 03
- No data files, templates, or schemas defined
- No error handling or fallback patterns

**Compliance gaps identified:**
- No workflow.md entry point file
- No step files with proper frontmatter (name, description, nextStepFile)
- No MANDATORY EXECUTION RULES sections
- No EXECUTION PROTOCOLS sections
- No menu handling logic defined
- No state tracking (stepsCompleted) integration
- No data/ folder with schemas or templates
- Missing web_bundle consideration for step file sizes

---

## Memory-Informed Discovery Notes

### Preserve (from established SKF patterns)

- 9-step pipeline with integration-centric design (mapping library connections, not just listing)
- Multi-file output structure matching SKF conventions (SKILL.md, context-snippet.md, metadata.json, references/)
- User confirmation gate at step 03 aligns with ADR-E smart scope pattern
- Parallel extraction at step 04 architecturally sound for multi-library processing
- Logical progression: detect → rank → confirm → extract → analyze → compile → write → validate → report

### Address (gaps identified from memory)

- `manifest_reader` does not exist — needs self-contained dependency detection with fallback chain (npm/PyPI/crates.io/Cargo registry APIs → file parsing → web search)
- No forge-tier awareness — must implement Quick/Forge/Forge+/Deep tier behavior matching create-skill, quick-skill, test-skill, export-skill patterns
- No tool bridge specifications — needs gh_bridge (all tiers), ast_bridge (Forge/Deep), qmd_bridge (Deep only)
- No error handling matrix — needs hard halt / graceful degradation / silent skip / advisory categories
- "Absorbs analyze-stack internally" undefined — must define concrete analyze-stack functionality within steps 01-05
- SKF module config.yaml does not exist yet — setup-forge prerequisite must create it

### Add (enhancements from ecosystem patterns)

- Forge-tier dependent extraction: Quick = source reading + basic import counting; Forge = ast_bridge for structural co-import detection; Deep = qmd_bridge for temporal integration evolution
- Confidence tier labeling (T1 AST-verified, T1-low source reading, T2 QMD-enriched) matching create-skill pattern
- Workflow chaining: prerequisite = setup-forge; downstream = test-skill, export-skill
- Positive capability framing in reporting ("Stack forged: {name} — {lib_count} libraries, {integration_count} integration patterns")
- Error handling matrix following established 7-scenario pattern from create-skill design

### Audience

- Ferris in Architect mode — consistent with spec and all SKF creation workflows
- Target: developers wanting consolidated view of how their project's dependencies integrate
- Phase 1b (Entry Points) build priority

---

## Classification Decisions

**Workflow Name:** create-stack-skill
**Target Path:** src/workflows/create-stack-skill/ (spec) / _bmad-output/bmb-creations/workflows/create-stack-skill/ (build output)

**4 Key Decisions:**
1. **Document Output:** false — compile-then-write action pattern (collects data steps 01-05, compiles step 06, writes step 07), consistent with create-skill classification
2. **Module Affiliation:** skf — SKF module, consistent with all Skill Forge workflows
3. **Session Type:** single-session — consistent with all SKF workflows; subprocess calls (max_parallel_generation) handle heavy lifting outside main context
4. **Lifecycle Support:** create-only — stack skills regenerated fresh when dependencies change, no incremental editing

**Structure Implications:**
- `steps-c/` only — no edit or validate folders
- Standard init step (no step-01b continuation)
- No stepsCompleted tracking in output (non-document, action-based)
- SKF module variables: `skills_output_folder`, `forge_data_folder`, `forge-tier`
- Subprocess support needed for `max_parallel_generation` at step 04
- Installed path: `{project-root}/_bmad/skf/workflows/create-stack-skill`

---

## Requirements

**Flow Structure:**
- Pattern: linear pipeline
- Phases: detect → rank → confirm → extract → analyze → compile → write → validate → report
- Estimated steps: 9 (matching spec)
- No looping or branching — straight through with confirmation gates

**User Interaction:**
- Style: mostly autonomous with strategic gates
- Decision points:
  - Gate 1 (Step 03): Scope confirmation — user confirms library list after ranking
  - Gate 2 (Step 06): Compile checkpoint — review assembled SKILL.md integration layer before writing
- Checkpoint frequency: 2 gates in 9-step pipeline (steps 03, 06)

**Inputs Required:**
- Required: Project root with dependency manifests (package.json, requirements.txt, Cargo.toml, go.mod, etc.)
- Required: setup-forge completed — forge-tier.yaml with tier and available tools
- Optional: Explicit dependency list (skip auto-detection)
- Optional: Scope overrides per library (include/exclude specific exports)

**Output Specifications:**
- Type: action (multi-file generation)
- Deliverable files in `{skills_output_folder}/{project}-stack/`:
  - SKILL.md — Integration patterns + conventions (main skill)
  - context-snippet.md — Compressed stack index (~50-80 tokens per lib, ADR-L v2)
  - metadata.json — skill_type: "stack", library list, integration pair count
  - references/{library}.md — Per-library API surface and key patterns
  - references/integrations/{pair}.md — Cross-library integration patterns
- Workspace artifacts in `{forge_data_folder}/{project}-stack/`:
  - provenance-map.json — Source tracking per library extraction
  - evidence-report.md — Extraction evidence and confidence breakdown
- Frequency: single run per project (re-run when dependencies change)

**Success Criteria:**
- All confirmed libraries have reference files generated
- Integration pairs documented for detected co-import patterns
- SKILL.md has meaningful integration layer (not concatenated library docs)
- All content has confidence tier labels (T1/T1-low/T2)
- context-snippet.md within target token budget
- metadata.json valid against agentskills.io spec
- Positive capability framing: "Stack forged: {name} — {lib_count} libraries, {integration_count} integration patterns"

**Instruction Style:**
- Overall: prescriptive
- Notes: Mechanical compilation pipeline with Ferris Architect mode. Steps 01-02, 04-09 are autonomous processing. Only step 03 has collaborative scope confirmation. Matches create-skill and quick-skill prescriptive patterns.

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** excluded — prescriptive mechanical pipeline, no creative facilitation needed
- **Advanced Elicitation:** excluded — same reasoning, consistent with all SKF workflows
- **Brainstorming:** excluded — same reasoning

**LLM Features:**
- **Web-Browsing:** included — fetching library documentation during extraction (Phase 3), checking registry APIs during manifest resolution (Phase 1)
- **File I/O:** included — essential for reading manifests (Phase 1) and writing all output files (Phase 6)
- **Sub-Agents:** excluded — not needed for linear pipeline
- **Sub-Processes:** included — essential for Phase 3 parallel extraction via max_parallel_generation

**Memory:**
- Type: single-session
- Tracking: sidecar-file (forge-tier.yaml from setup-forge, read-only)

**External Integrations (pre-detected by setup-forge):**
- `gh_bridge` (all tiers) — GitHub API for repository access and source reading
- `ast_bridge` (Forge/Deep tiers) — ast-grep for structural import/export analysis and co-import detection
- `qmd_bridge` (Deep tier only) — QMD for temporal integration evolution patterns
- `skill-check` — agentskills.io spec validation (Step 08): `npx skill-check check --fix --format json` for validation + auto-fix + quality scoring, `split-body` for oversized body remediation, security scan for prompt injection detection

**Installation Requirements:**
- None new — all tools pre-detected by setup-forge prerequisite workflow
- User preference: no additional installation needed

---

## Workflow Design

### File Structure

```
create-stack-skill/
├── workflow.md                          (entry point, Ferris Architect mode)
├── data/
│   ├── manifest-patterns.md             (detection patterns per language ecosystem)
│   ├── integration-patterns.md          (co-import detection rules and known pairs)
│   └── stack-skill-template.md          (SKILL.md section structure)
└── steps-c/
    ├── step-01-init.md                  (Init Non-Continuable with discovery)
    ├── step-02-detect-manifests.md      (Middle Simple, auto-proceed)
    ├── step-03-rank-and-confirm.md      (Middle Simple, P2 Gate 1)
    ├── step-04-parallel-extract.md      (Middle Simple, auto-proceed, subprocess)
    ├── step-05-detect-integrations.md   (Middle Simple, auto-proceed)
    ├── step-06-compile-stack.md         (Middle Simple, P2 Gate 2)
    ├── step-07-generate-output.md       (Middle Simple, auto-proceed)
    ├── step-08-validate.md              (Middle Simple, auto-proceed)
    └── step-09-report.md               (Final)
```

### Step Sequence Table

| Step | Name | Type | Menu | Key Refs |
|------|------|------|------|----------|
| 01 | init | Init Non-Continuable (discovery) | P3 auto-proceed | skfConfig, forgeTierFile |
| 02 | detect-manifests | Middle Simple | P3 auto-proceed | manifestPatterns |
| 03 | rank-and-confirm | Middle Simple | P2 C-only (Gate 1) | — |
| 04 | parallel-extract | Middle Simple | P3 auto-proceed | — |
| 05 | detect-integrations | Middle Simple | P3 auto-proceed | integrationPatterns |
| 06 | compile-stack | Middle Simple | P2 C-only (Gate 2) | stackSkillTemplate |
| 07 | generate-output | Middle Simple | P3 auto-proceed | — |
| 08 | validate | Middle Simple | P3 auto-proceed | — |
| 09 | report | Final | No nextStepFile | — |

### Step Action Plans

**Step 01 (init):**
- Load SKF module config from `_bmad/skf/config.yaml`
- Load forge-tier.yaml from sidecar: determine Quick/Forge/Forge+/Deep tier and available tools
- Validate prerequisites: forge-tier.yaml exists, project root accessible
- Accept optional explicit dependency list (skip auto-detection if provided)
- Accept optional scope overrides per library
- Display init summary: project name, tier, available tools
- Auto-proceed to step 02

**Step 02 (detect-manifests):**
- Scan project root for dependency manifest files using manifest-patterns.md:
  - JavaScript: package.json, package-lock.json
  - Python: requirements.txt, setup.py, pyproject.toml, Pipfile
  - Rust: Cargo.toml
  - Go: go.mod
  - Java: pom.xml, build.gradle
  - Ruby: Gemfile
  - (extensible via data file)
- Parse each manifest to extract dependency names and version constraints
- If explicit dependency list provided in step 01, skip detection and use that list
- Report: found X manifests, Y total dependencies
- Auto-proceed to step 03

**Step 03 (rank-and-confirm) — Gate 1:**
- Count import/require statements per dependency across codebase (Pattern 1 subprocess grep)
- Rank dependencies by import frequency (descending)
- Filter out trivially-used dependencies (< threshold imports)
- Present ranked table: library name, import count, manifest source
- User confirms which dependencies to include/exclude
- Gate 1: P2 C-only to confirm scope and proceed

**Step 04 (parallel-extract):**
- For each confirmed dependency, launch subprocess extraction (Pattern 4 parallel, max_parallel_generation):
  - Quick tier: Read source files importing the library, extract usage patterns via source reading
  - Forge tier: ast_bridge for structural export analysis, function signatures, type definitions
  - Deep tier: qmd_bridge for temporal usage evolution, deprecated patterns, API migration history
- Each subprocess returns: library name, key exports, usage patterns, confidence tier label
- Aggregate results, report extraction summary (X libraries extracted, confidence distribution)
- Auto-proceed to step 05

**Step 05 (detect-integrations):**
- For each pair of confirmed libraries, detect co-import patterns:
  - Files that import both libraries (Pattern 1 subprocess grep)
  - Shared type definitions between libraries
  - Middleware/pipeline chains involving multiple libraries
  - Configuration bridges (one library configuring another)
  - Event handler patterns crossing library boundaries
- Use integration-patterns.md for known integration pattern templates
- Build integration graph: nodes = libraries, edges = integration points with descriptions
- Auto-proceed to step 06

**Step 06 (compile-stack) — Gate 2:**
- Load stack-skill-template.md for SKILL.md section structure
- Compile SKILL.md:
  - Header: project name, library count, integration summary
  - Integration layer: cross-cutting patterns, middleware chains, shared types, config bridges
  - Per-library sections: key exports, usage conventions, gotchas, confidence annotations
  - Confidence tier labels throughout (T1 AST-verified, T1-low source reading, T2 QMD-enriched)
- Present compiled SKILL.md preview to user for review
- Gate 2: P2 C-only to confirm compilation and proceed to writing

**Step 07 (generate-output):**
- Write all deliverable files to `{skills_output_folder}/{project}-stack/`:
  - SKILL.md (from compilation)
  - context-snippet.md (~50-80 tokens per library, ADR-L v2 format)
  - metadata.json (skill_type: "stack", library list, integration pair count, version)
  - references/{library}.md for each confirmed library
  - references/integrations/{pair}.md for each detected integration pair
- Write workspace artifacts to `{forge_data_folder}/{project}-stack/`:
  - provenance-map.json (source tracking per library extraction)
  - evidence-report.md (extraction evidence and confidence breakdown)
- Auto-proceed to step 08

**Step 08 (validate):**
- Validate output against agentskills.io spec via skill-check
- Check: SKILL.md structure, metadata.json required fields, reference file completeness
- Verify all confidence tier labels present
- Report validation results (pass/fail with specific findings)
- Advisory: show warnings but continue to report
- Auto-proceed to step 09

**Step 09 (report) — Final:**
- Display: "Stack forged: {name} — {lib_count} libraries, {integration_count} integration patterns"
- Show confidence distribution table (T1/T1-low/T2 counts with descriptions)
- List all output files with purposes
- Conditional warnings display (only if warnings exist)
- Recommend next workflows: [TS] Test Skill, [ES] Export Skill
- Workflow complete

### Data Flow

```
step-01: tier, tools, optional_dep_list
  → step-02: manifests[], raw_dependencies[]
  → step-03: confirmed_dependencies[] (user-approved scope)
  → step-04: per_library_extractions[] (exports, patterns, confidence)
  → step-05: integration_graph {pairs[], shared_types[], chains[]}
  → step-06: skill_content (compiled SKILL.md)
  → step-07: written_files[] (all output artifacts)
  → step-08: validation_result {pass/fail, findings[]}
  → step-09: summary (console report)
```

### Error Handling Matrix

| Scenario | Response |
|----------|----------|
| Missing forge-tier.yaml | Hard halt: "Run setup-forge first" |
| No manifests found | Hard halt: "No dependency manifests detected in project" |
| Inaccessible source code | Hard halt: "Cannot access source repository" |
| Library extraction failure (single) | Graceful degradation: skip library, note in report |
| No integrations detected | Graceful: "No co-import patterns found, stack contains library summaries only" |
| Validation failures | Advisory: show warnings, continue to report |
| Individual file write failure | Hard halt per file |

### Workflow Chaining

- **Prerequisites:** setup-forge (required — provides forge-tier.yaml)
- **Optional inputs:** skill-brief.yaml files for individual libraries (from brief-skill)
- **Downstream:** [TS] test-skill (recommended), [ES] export-skill (recommended)
- No prerequisites from brief-skill or create-skill (this is an independent entry point)

### Subprocess Optimization

| Step | Pattern | Operation | Returns |
|------|---------|-----------|---------|
| 03 | Pattern 1 (Grep) | Count imports per library across codebase | `{library: import_count}` pairs |
| 04 | Pattern 4 (Parallel) | Per-library extraction (max_parallel_generation) | Structured extraction per library |
| 05 | Pattern 1 (Grep) | Co-import file detection per library pair | File lists with co-imports |

Fallback for all: if subprocess unavailable, perform operations in main context thread.

### Role and Persona

- Ferris Architect mode — prescriptive precision execution
- Speed-first, zero hallucination: all content traces to actual code with file:line citations
- No creative facilitation, no A/P menus
- Positive capability framing in reporting

---

## Foundation Build Complete

**Created:**
- Folder structure at: `_bmad-output/bmb-creations/workflows/create-stack-skill/`
- `workflow.md` — Entry point with Ferris Architect mode, SKF config loading, zero-hallucination rules
- `data/manifest-patterns.md` — Detection patterns for 8 language ecosystems with import counting rules
- `data/integration-patterns.md` — 6 integration pattern types with detection signals and output format
- `data/stack-skill-template.md` — SKILL.md structure, context-snippet format, metadata.json schema, reference file structures

**Configuration:**
- Workflow name: create-stack-skill
- Continuable: no (single-session)
- Document output: no (action-based, multi-file generation)
- Mode: create-only (steps-c/ only)
- No output template needed (non-document)

**Next Steps:**
- Step 8: Build step-01-init.md
- Step 9: Build remaining steps 02-09 (iterative)

---

## Step 01 Build Complete

**Created:**
- steps-c/step-01-init.md

**Step Configuration:**
- Type: Init Non-Continuable (with input discovery for forge-tier.yaml)
- Input Discovery: yes (forge-tier.yaml from sidecar, optional explicit dependency list)
- Menu: P3 auto-proceed (no A/P, no user interaction)
- Next Step: step-02-detect-manifests

**No supporting files needed** — data files already created in foundation (manifest-patterns.md, integration-patterns.md, stack-skill-template.md)

---

## Steps 02-09 Build Complete

**All workflow steps built in sequence:**

| Step | File | Type | Menu |
|------|------|------|------|
| 02 | step-02-detect-manifests.md | Middle Simple | P3 auto-proceed |
| 03 | step-03-rank-and-confirm.md | Middle Simple | P2 C-only (Gate 1) |
| 04 | step-04-parallel-extract.md | Middle Simple | P3 auto-proceed |
| 05 | step-05-detect-integrations.md | Middle Simple | P3 auto-proceed |
| 06 | step-06-compile-stack.md | Middle Simple | P2 C-only (Gate 2) |
| 07 | step-07-generate-output.md | Middle Simple | P3 auto-proceed |
| 08 | step-08-validate.md | Middle Simple | P3 auto-proceed |
| 09 | step-09-report.md | Final | No nextStepFile |

**Subprocess Optimization Applied:**
- Step 03: Pattern 1 (Grep) — import counting across codebase
- Step 04: Pattern 4 (Parallel) — per-library extraction via max_parallel_generation
- Step 05: Pattern 1 (Grep) — co-import file detection per library pair

**User Gates:**
- Gate 1 (Step 03): Scope confirmation — user confirms library list after ranking
- Gate 2 (Step 06): Compile checkpoint — review SKILL.md integration layer before writing

**Supporting Files (created in foundation):**
- data/manifest-patterns.md — 8 ecosystem detection patterns
- data/integration-patterns.md — 6 integration type classifications
- data/stack-skill-template.md — SKILL.md, context-snippet, metadata, reference structures

**All 9 workflow steps + 3 data files + workflow.md entry point = complete workflow build.**
