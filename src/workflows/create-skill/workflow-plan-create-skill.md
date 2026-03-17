---
conversionFrom: 'src/workflows/create-skill/create-skill.spec.md'
originalFormat: 'Workflow Specification (placeholder)'
stepsCompleted: ['step-00-conversion', 'step-02-classification', 'step-03-requirements', 'step-04-tools', 'step-05-plan-review', 'step-06-design', 'step-07-foundation', 'step-08-build-step-01', 'step-09-build-all-steps', 'step-10-confirmation', 'step-11-completion']
created: 2026-02-26
completionDate: 2026-02-26
status: COMPLETE
approvedDate: 2026-02-26
confirmationDate: 2026-02-26
confirmationType: conversion
coverageStatus: complete
---

# Workflow Creation Plan

## Conversion Source

**Original Path:** src/workflows/create-skill/create-skill.spec.md
**Original Format:** Workflow Specification / Placeholder (pre-implementation spec from module build step-05)
**Detected Structure:** Single spec file with 8 planned steps, input/output contracts, agent integration notes. No workflow.md, no step files, no templates, no data files.

---

## Original Workflow Analysis

### Goal (from source)

Compile a skill from a brief — the core compilation engine. Takes a skill-brief.yaml and source code, extracts function signatures and type definitions via AST analysis, enriches with QMD knowledge (Deep tier), validates against agentskills.io spec, and produces a complete SKILL.md with provenance map and evidence report. Supports `--batch` for multiple briefs.

### Original Steps (Complete List)

**Step 1:** load-brief — Load and validate skill-brief.yaml, resolve source code location
**Step 2:** ecosystem-check — Search if official skill already exists (advisory, not blocking)
**Step 3:** extract — AST extraction of exports, signatures, types (tier-dependent: Quick=source reading, Forge=AST, Deep=AST)
**Step 4:** enrich — QMD knowledge search for temporal context (Deep tier only, skip for Quick/Forge)
**Step 5:** compile — Assemble SKILL.md sections from extracted data with confidence tiers
**Step 6:** validate — Validate against agentskills.io spec via skill-check tool
**Step 7:** generate-artifacts — Write SKILL.md, provenance-map.json, evidence-report.md, metadata.json, context-snippet.md, extraction-rules.yaml
**Step 8:** report — Display compilation summary with confidence tiers, suggest next steps

### Output / Deliverable

7 output files across two directory trees:

**skills/{name}/ (deliverables):**
- SKILL.md — Active skill (trigger-based)
- context-snippet.md — Passive context source template
- metadata.json — Machine-readable birth certificate
- references/ — Progressive disclosure files per function

**forge-data/{name}/ (workspace artifacts):**
- provenance-map.json — Source map, AST bindings
- evidence-report.md — Build artifact, audit trail
- extraction-rules.yaml — Language + ast-grep schema

### Input Requirements

**Required:**
- `{forge_data_folder}/{skill-name}/skill-brief.yaml` — Compilation config from brief-skill workflow
- Source code (local path or GitHub repo URL)

**Optional:**
- `--batch` flag with list of briefs or directory path
- `--continue` flag for resuming interrupted batch operations

### Key Instructions to LLM

- Ferris operates in **Architect mode** — exploratory, structural, assembling
- Structured reports with inline AST citations during work, no metaphor
- Zero hallucination tolerance — every instruction traces to code
- Confidence tier labeling: T1 (AST extraction), T2 (QMD evidence), T3 (external docs)
- Positive capability framing — describe what the tier enables, not what's missing
- Tool invisibility — tools are backstage, results are center stage

---

## Conversion Notes

**What works well in original:**
- Clean 8-step decomposition with single-responsibility boundaries
- Tier-dependent behavior design at steps 03/04
- Dual-output architecture (skills/ for deliverables, forge-data/ for workspace)
- agentskills.io spec compliance as first-class concern
- Confidence tier system (T1/T2/T3) well-defined in module brief
- Progressive disclosure via references/ directory

**What needs improvement:**
- Spec incorrectly marks as "document-producing" — this is a multi-file action workflow
- Quick tier fallback for step-03 needs explicit design (source reading via gh_bridge)
- No detail on how --batch works (loop wrapper? sub-process per brief?)
- Ecosystem check nuances missing (5-second timeout, 24-hour cache, advisory not blocking)
- No error handling patterns defined
- No sidecar checkpointing design for --continue recovery

**Compliance gaps identified:**
- No workflow.md entry point
- No step files in steps-c/ directory
- No BMAD frontmatter with stepsCompleted tracking
- No menu/auto-proceed patterns defined
- No data files or templates
- No tier-dependent conditional logic architecture
- Missing [MANUAL] section marker seeding for future update-skill compatibility

**Deduced interaction model:**
- Mostly autonomous with 2 strategic confirmation gates
- Gate 1: After ecosystem check — if official skill found, user decides (proceed/abort/install existing)
- Gate 2: After extraction — show findings (export count, confidence breakdown) before compilation
- All other steps auto-proceed
- Matches module brief use case stories (47s Quick, 8min batch)

---

## Classification Decisions

**Workflow Name:** create-skill
**Target Path:** _bmad-output/bmb-creations/workflows/create-skill/ (build location)
**Installed Path:** {project-root}/_bmad/skf/workflows/skillforge/create-skill/ (per Ferris agent menu)

**4 Key Decisions:**
1. **Document Output:** false — action-based workflow producing multiple files as side effects, not a progressively-built document. Steps accumulate data in context, step-07 writes all files at once.
2. **Module Affiliation:** SKF — part of the Skill Forge module, invoked through Ferris agent [CS] trigger, has access to SKF config variables (forge tier, tool availability, sidecar paths).
3. **Session Type:** single-session — primary use case is fast (47s Quick, minutes for Forge/Deep). Batch mode (`--batch`) is a loop wrapper repeating single-session runs, not a reason for continuable architecture. `--continue` resumes the batch loop via sidecar checkpointing.
4. **Lifecycle Support:** create-only — SKF splits lifecycle across specialized workflows: update-skill (edits/Surgeon mode), test-skill (validation/Audit mode), audit-skill (drift detection). No tri-modal needed.

**Structure Implications:**
- Only `steps-c/` directory needed
- No `step-01b-continue.md` (single-session)
- No `stepsCompleted` tracking in output (non-document)
- No templates directory (non-document)
- Data directory needed for shared reference files (extraction patterns, spec schema references)
- Standard `step-01-init.md` with no continuation logic

---

## Requirements

**Flow Structure:**
- Pattern: Linear with conditional branches within steps (tier-dependent)
- Phases: Load → Check → Extract → Enrich → Compile → Validate → Generate → Report
- Estimated steps: 8
- Conditional logic: Steps 03/04 branch internally by forge tier (Quick/Forge/Deep)
- No branching steps — conditions stay within each step

**User Interaction:**
- Style: Mostly autonomous with 2 strategic confirmation gates
- Gate 1 (step-02): If ecosystem check finds official skill — user decides: proceed / abort / install existing. No match = auto-proceed silently.
- Gate 2 (step-03): After extraction — display export count, confidence breakdown, tier used. User confirms before compilation.
- All other steps: Auto-proceed with no user interaction
- Checkpoint frequency: Only at the 2 gates above

**Inputs Required:**
- Required: `forge-data/{skill-name}/skill-brief.yaml` (from brief-skill workflow)
- Required: Source code location (local path or GitHub owner/repo)
- Prerequisite: `setup-forge` must have run — `forge-tier.yaml` must exist in sidecar
- Optional: `--batch` flag (list of briefs or directory for batch compilation)
- Optional: `--continue` flag (resume interrupted batch from sidecar checkpoint)

**Output Specifications:**
- Type: Multi-file action — 7 files written to 2 directory trees
- skills/{name}/: SKILL.md, context-snippet.md, metadata.json, references/
- forge-data/{name}/: provenance-map.json, evidence-report.md, extraction-rules.yaml
- Frequency: Single skill per run; batch mode loops the workflow per brief
- [MANUAL] markers: Seed empty `<!-- [MANUAL] -->` sections in SKILL.md for future update-skill compatibility

**Success Criteria:**
- All 7 output files generated without errors
- SKILL.md validates against agentskills.io spec (via skill-check)
- Every instruction has provenance citation with confidence tier (T1/T2/T3)
- Zero hallucinated content — uncitable claims excluded, not guessed
- Confidence tier distribution reported (e.g., "20 T1, 3 T2, 0 T3")
- Forge completion message: "Skill forged: {name} v{version} — {count} functions, T1 confidence."

**Instruction Style:**
- Overall: Prescriptive — compilation pipeline with exact operations
- Tool commands specific (ast-grep scan, QMD search, gh read)
- File operations exact with defined paths and formats
- Matches setup-forge prescriptive pattern: deterministic operations, specific commands, conditional logic
- Notes: Ferris Architect mode communication style during execution (structured reports, AST citations, no metaphor except at transitions)

---

## Tools Configuration

**Core BMAD Tools:**
- **Party Mode:** Excluded — prescriptive compilation pipeline, no creative exploration phases
- **Advanced Elicitation:** Excluded — no facilitative deep-dive phases in a compilation workflow
- **Brainstorming:** Excluded — no ideation phases, all steps are deterministic operations

**LLM Features:**
- **Web-Browsing:** Excluded — source access via gh_bridge, ecosystem check via skill-check. No raw web needed.
- **File I/O:** Included — essential. Reads skill-brief.yaml, forge-tier.yaml, source files. Writes 7 output files across 2 directory trees (skills/{name}/, forge-data/{name}/).
- **Sub-Agents:** Excluded — linear pipeline with step dependencies, no parallelizable specialized tasks for single skill compilation
- **Sub-Processes:** Excluded — sequential dependency chain. Batch mode is a loop wrapper, not parallel processes.

**Memory:**
- Type: Single-session
- Reads forge-tier.yaml from sidecar at init (existing state from setup-forge)
- Batch --continue: checkpoint progress in sidecar (batch-progress.yaml)
- No stepsCompleted tracking (non-document workflow)

**External Integrations (SKF MCP Tools — all pre-detected by setup-forge):**
- **gh_bridge:** Required all tiers — source reading, file trees, issues, releases, changelog
- **skill-check:** Required all tiers — `npx skill-check check --fix --format json` for validation + auto-fix + quality scoring (0-100), `--no-security-scan` for fast validation, security scan for prompt injection detection, `split-body` for oversized body remediation
- **ast_bridge:** Required Forge/Deep tiers — AST scan_definitions, run_rule, detect_co_imports
- **qmd_bridge:** Required Deep tier only — search, vector_search, deep_search for temporal context

**Installation Requirements:**
- All tools pre-detected by setup-forge workflow
- No new installations needed — workflow reads forge-tier.yaml to know what's available
- Graceful degradation: if tier is Quick, AST and QMD steps skip automatically

---

## Workflow Design

### File Structure

```
create-skill/
├── workflow.md                         (entry point, ~50 lines)
├── workflow-plan-create-skill.md       (this plan file)
├── data/
│   ├── skill-sections.md               (SKILL.md section structure + agentskills.io format)
│   └── extraction-patterns.md          (tier-specific extraction instructions)
└── steps-c/
    ├── step-01-load-brief.md           (~150 lines, Init with Input Discovery)
    ├── step-02-ecosystem-check.md      (~120 lines, conditional gate)
    ├── step-03-extract.md              (~200 lines, complex middle)
    ├── step-03b-fetch-temporal.md      (~240 lines, conditional auto-proceed)
    ├── step-03c-fetch-docs.md          (~215 lines, conditional auto-proceed)
    ├── step-04-enrich.md               (~130 lines, conditional middle)
    ├── step-05-compile.md              (~200 lines, complex middle)
    ├── step-06-validate.md             (~120 lines, simple middle)
    ├── step-07-generate-artifacts.md   (~180 lines, simple middle)
    └── step-08-report.md               (~120 lines, final)
```

### Step Sequence Table

| Step | Name | Type | Menu Pattern | Goal |
|------|------|------|-------------|------|
| 01 | load-brief | Init (Input Discovery) | Auto-proceed (P3) | Load brief, resolve source, load forge tier |
| 02 | ecosystem-check | Middle (Simple) | Conditional: auto if no match, user choice if match | Check ecosystem |
| 03 | extract | Middle (Standard) | C only (P2) — Gate 2 | Tier-dependent extraction |
| 03b | fetch-temporal | Middle (Simple) | Auto-proceed (P3) — Deep only | Fetch temporal context (issues, PRs, changelogs) and index into QMD |
| 03c | fetch-docs | Middle (Simple) | Auto-proceed (P3) — when doc_urls present | Fetch remote documentation from brief-specified URLs for T3-confidence content |
| 04 | enrich | Middle (Simple) | Auto-proceed (P3) — Deep only | QMD enrichment |
| 05 | compile | Middle (Simple) | Auto-proceed (P3) | Assemble SKILL.md |
| 06 | validate | Middle (Simple) | Auto-proceed (P3) | Validate spec |
| 07 | generate-artifacts | Middle (Simple) | Auto-proceed (P3) | Write output files |
| 08 | report | Final | None | Summary + next step |

### Step Action Plans

**step-01-load-brief** (Init with Input Discovery)
- Search forge-data/ for skill-brief.yaml matching user's request
- If --batch: discover all briefs in specified directory
- Load and validate brief structure (required fields: name, version, source_repo, language, scope)
- Resolve source code location (local path or GitHub owner/repo)
- Load forge-tier.yaml from sidecar — determine tier (Quick/Forge/Deep)
- If forge-tier.yaml missing: halt with "Run [SF] Setup Forge first"
- Auto-proceed to step-02

**step-02-ecosystem-check** (Conditional Gate)
- Query agentskills.io registry API for brief.name — 5-second timeout, 24-hour cache
- If match found: present to user with [P] Proceed / [I] Install existing / [A] Abort
- If no match OR timeout: auto-proceed silently
- If registry API unavailable: skip silently (API unavailability is not an error)
- Note: ecosystem lookup requires registry API, not `skill-check` CLI (which validates local skills only)

**step-03-extract** (Standard Middle — Gate 2)
- Load extraction-patterns.md data file
- Quick tier: source reading via gh_bridge (list_tree + read_file), infer exports. T1-low confidence.
- Forge/Deep tier: ast_bridge.scan_definitions() + detect_co_imports(). T1 confidence.
- Build extraction inventory: export count, signatures, types, confidence breakdown
- Present summary, user confirms [C] Continue

**step-03b-fetch-temporal** (Simple Middle — Conditional Auto-proceed)
- Deep tier only — Quick/Forge skip silently
- GitHub repos only — non-GitHub sources skip silently
- Fetch temporal context (issues, PRs, releases, changelog) via `gh` CLI
- Targeted function searches using top_exports from extraction inventory
- Index fetched content into QMD collection (`{skill-name}-temporal`)
- Register collection in forge-tier.yaml; clean up staging directory
- Cache-aware: skip re-fetch if collection < 7 days old
- All failures degrade gracefully — never blocks the workflow

**step-03c-fetch-docs** (Simple Middle — Conditional Auto-proceed)
- Runs at any tier when `doc_urls` are present in the brief
- Tool-agnostic: uses whatever web fetching capability is available (Firecrawl, WebFetch, web-reader, curl, etc.)
- Fetches remote documentation from brief-specified URLs for T3-confidence content
- Root URL detection: discovers and fetches relevant subpages for documentation sites
- All extracted items cited as T3 with `[EXT:{url}]` provenance
- T3 items never override existing T1/T1-low/T2 extractions
- Supports docs-only briefs (T3 inventory replaces empty extraction inventory)
- Deep tier: indexes fetched docs into QMD collection (`{skill-name}-docs`)
- All failures degrade gracefully — never blocks the workflow

**step-04-enrich** (Simple Middle — Conditional)
- Deep tier: QMD searches per extracted function — issues, PRs, changelogs. T2 annotations.
- Not Deep: skip silently, auto-proceed
- QMD failure: degrade gracefully, continue without enrichment

**step-05-compile** (Simple Middle)
- Load skill-sections.md data file
- Assemble SKILL.md: frontmatter, overview, quick start, API sections, [MANUAL] markers
- Generate references/ content per function/type
- Generate context-snippet.md (compressed 2-line format)
- Auto-proceed

**step-06-validate** (Simple Middle)
- `npx skill-check check --fix --format json` (schema + frontmatter + auto-fix + quality score)
- Pass: auto-proceed. Fail: attempt auto-fix, re-validate, halt if still failing.
- skill-check unavailable: skip automated validation, add warning to evidence report

**step-07-generate-artifacts** (Simple Middle)
- Create directories: skills/{name}/, skills/{name}/references/, forge-data/{name}/
- Write 4 deliverables to skills/{name}/
- Write 3 workspace artifacts to forge-data/{name}/
- Auto-proceed

**step-08-report** (Final)
- Display: skill name, version, source, export count, confidence distribution, tier, file list, warnings
- Forge completion: "Skill forged: {name} v{version} — {count} functions, T1 confidence."
- Suggest next: "[TS] Test Skill — verify completeness before export"
- No nextStepFile (final)

### Data Flow

```
step-01  READS: forge-tier.yaml, skill-brief.yaml
         SETS:  tier, brief_data, source_location
              ↓
step-02  READS: agentskills.io registry API (ecosystem check — not skill-check CLI)
         SETS:  ecosystem_status
              ↓
step-03  READS: source code via gh_bridge/ast_bridge
         SETS:  extraction_inventory
              ↓
step-03b READS: source_repo via gh CLI, top_exports from extraction_inventory (Deep only)
         CREATES: QMD temporal collection ({skill-name}-temporal)
              ↓
step-03c READS: doc_urls from brief_data (when present, any tier)
         SETS:  T3 items merged into extraction_inventory
              ↓
step-04  READS: QMD collections (Deep only)
         SETS:  enrichment_annotations
              ↓
step-05  READS: extraction_inventory + enrichment_annotations
         BUILDS: skill_content
              ↓
step-06  READS: skill_content
         VALIDATES: agentskills.io spec
              ↓
step-07  READS: skill_content + validation_result
         WRITES: 7 output files
              ↓
step-08  DISPLAYS: compilation summary
```

### Error Handling

| Error Type | Response | Pattern |
|-----------|----------|---------|
| Missing forge-tier.yaml | Halt: "Run [SF] Setup Forge first" | Hard prerequisite |
| Missing skill-brief.yaml | Halt: "Run [BS] Brief Skill first, or [QS] Quick Skill" | Hard prerequisite |
| Tool unavailable | Degrade to lower tier silently | Graceful degradation |
| Ecosystem check timeout | Skip silently, proceed | Advisory, not blocking |
| AST extraction file failure | Log warning, skip file, continue | Partial success |
| Spec validation failure | Report, auto-fix, re-validate | Retry once |
| File write failure | Halt with specific error | Real error |

### Workflow Chaining

- Previous: brief-skill (produces skill-brief.yaml) — required
- Prerequisite: setup-forge (produces forge-tier.yaml) — required
- Alternative entry: quick-skill bypasses brief, invokes create-skill internally
- Next recommended: test-skill → export-skill

### Subprocess Optimization

No high-priority opportunities. Linear pipeline with tool-delegated heavy lifting.
Low-priority: Pattern 4 could parallelize batch --batch per-brief, not primary use case.

---

## Step 01 Build Complete

**Created:**
- steps-c/step-01-load-brief.md (~175 lines)

**Step Configuration:**
- Type: Init with Input Discovery (non-continuable)
- Menu: Auto-proceed (P3) — no user interaction
- Next Step: step-02-ecosystem-check.md

**Key Design Decisions:**
- Frontmatter references forgeTierFile and extractionPatternsData
- 6-section mandatory sequence: Load Forge Tier → Discover Skill Brief → Validate Brief Structure → Resolve Source Code Location → Report Initialization → Auto-proceed
- Handles --batch flag for batch brief discovery
- Positive capability framing for tier descriptions
- Required brief fields: name, version, source_repo, language, scope
- Halt with actionable errors if prerequisites missing

## Step 02 Build Complete

**Created:**
- steps-c/step-02-ecosystem-check.md (~110 lines)

**Step Configuration:**
- Type: Middle (Simple) — Conditional Gate
- Menu: Conditional — auto-proceed if no match, custom [P]/[I]/[A] if match found
- Next Step: step-03-extract.md

**Key Design Decisions:**
- Advisory, never blocking — tool failures and timeouts are silent skips
- 5-second timeout on ecosystem queries, 24-hour cache
- Custom menu only appears when a match is found (not standard A/P/C)
- Three user options on match: Proceed / Install existing / Abort

## Step 03 Build Complete

**Created:**
- steps-c/step-03-extract.md (~170 lines)

**Step Configuration:**
- Type: Middle (Standard) — Gate 2 confirmation
- Menu: C only after extraction summary presentation
- Next Step: step-04-enrich.md

**Key Design Decisions:**
- Tier-dependent extraction: Quick (source reading, T1-low) vs Forge/Deep (AST, T1)
- Graceful degradation if AST tools unavailable at Forge tier
- Per-file failure handling: skip and continue
- Extraction inventory with aggregate counts and confidence breakdown
- Gate 2: user must confirm extraction findings before compilation
- Zero hallucination — every export must have provenance citation

## Step 04 Build Complete

**Created:**
- steps-c/step-04-enrich.md (~115 lines)

**Step Configuration:**
- Type: Middle (Simple) — Conditional auto-proceed
- Menu: Auto-proceed (P3) — no user interaction
- Next Step: step-05-compile.md

**Key Design Decisions:**
- Deep tier only — Quick/Forge skip silently with no output
- QMD searches per function: issues/PRs, changelog, migration/deprecation
- T2 annotations with temporal classification (T2-past, T2-future)
- Additive only — never modifies T1 extraction data
- QMD failures degrade gracefully

## Step 05 Build Complete

**Created:**
- steps-c/step-05-compile.md (~175 lines)

**Step Configuration:**
- Type: Middle (Simple) — auto-proceed
- Menu: Auto-proceed (P3)
- Next Step: step-06-validate.md

**Key Design Decisions:**
- Loads skill-sections.md data file for agentskills.io format
- Assembles all 7 content artifacts in context (no file writes)
- [MANUAL] markers seeded for update-skill compatibility
- Zero hallucination enforcement — no fabricated examples
- References grouped by module/file/functional area

## Step 06 Build Complete

**Created:**
- steps-c/step-06-validate.md (~120 lines)

**Step Configuration:**
- Type: Middle (Simple) — auto-proceed
- Menu: Auto-proceed (P3)
- Next Step: step-07-generate-artifacts.md

**Key Design Decisions:**
- skill-check validation: `check --fix --format json` (schema + frontmatter + quality score + auto-fix + security scan)
- Auto-fix pattern: validate → fix → re-validate (once per failure)
- Tool unavailability: skip with warning, not halt
- Validation failures are warnings — proceed to generation
- Results recorded in evidence-report content

## Step 07 Build Complete

**Created:**
- steps-c/step-07-generate-artifacts.md (~130 lines)

**Step Configuration:**
- Type: Middle (Simple) — auto-proceed
- Menu: Auto-proceed (P3)
- Next Step: step-08-report.md

**Key Design Decisions:**
- Creates directory structure: skills/{name}/, forge-data/{name}/
- Writes all 7 files from compiled content in context
- Write-only step — no content modification
- File write failures are real errors (halt, not degrade)
- Verification step confirms all files exist

## Step 08 Build Complete

**Created:**
- steps-c/step-08-report.md (~140 lines)

**Step Configuration:**
- Type: Final — no next step
- Menu: None (final step)
- Next Step: N/A

**Key Design Decisions:**
- Forge completion banner: "Skill forged: {name} v{version}"
- Full compilation summary with confidence distribution table
- All output file paths listed
- Next steps: test-skill, export-skill, update-skill
- Context snippet provided for immediate CLAUDE.md use
- Batch mode: loop back to step-01 for remaining briefs
