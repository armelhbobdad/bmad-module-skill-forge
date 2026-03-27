# SKF Workflows

Twelve workflows covering the full skill lifecycle — from source discovery through verified export, with pre-code architecture verification.

All workflows are triggered via Ferris (`@Ferris <code>`) and execute as step-by-step sequences with just-in-time step loading.

## Workflow Index

| Code | Workflow | Steps | Mode | Purpose |
| --- | --- | --- | --- | --- |
| SF | [setup-forge](setup-forge/workflow.md) | 5 | Architect | Initialize environment, detect tools, set capability tier |
| AN | [analyze-source](analyze-source/workflow.md) | 7 | Architect | Discover skillable units in a repo, produce recommended briefs |
| BS | [brief-skill](brief-skill/workflow.md) | 5 | Architect | Design a skill scope through guided discovery |
| CS | [create-skill](create-skill/workflow.md) | 8 | Architect | Compile a skill from brief with provenance (supports --batch) |
| QS | [quick-skill](quick-skill/workflow.md) | 6 | Architect | Fast skill from package name or GitHub URL — no brief needed |
| SS | [create-stack-skill](create-stack-skill/workflow.md) | 9 | Architect | Consolidated project stack skill with integration patterns (code-mode + compose-mode) |
| VS | [verify-stack](verify-stack/workflow.md) | 6 | Audit | Validate tech stack feasibility against architecture and PRD |
| RA | [refine-architecture](refine-architecture/workflow.md) | 6 | Architect | Improve architecture doc using verified skill data |
| US | [update-skill](update-skill/workflow.md) | 7 | Surgeon | Regenerate after source changes, preserving \[MANUAL\] sections |
| AS | [audit-skill](audit-skill/workflow.md) | 6 | Audit | Drift detection between skill and current source code |
| TS | [test-skill](test-skill/workflow.md) | 7 | Audit | Cognitive completeness verification — quality gate before export |
| EX | [export-skill](export-skill/workflow.md) | 6 | Delivery | Package for distribution, inject into CLAUDE.md/AGENTS.md |

## Typical Flows

**First-time setup:**

```
SF → AN → CS (batch) → TS → EX
```

**Single skill (full quality):**

```
SF → BS → CS → TS → EX
```

**Single skill (fast):**

```
SF → QS → EX
```

**Pre-code stack verification:**

```
SF → CS×N (per library) → VS → RA → SS (compose) → TS → EX
```

**Maintenance:**

```
AS → US → TS → EX
```

## Knowledge vs. Data

The module uses two kinds of reference material, loaded just-in-time during workflow execution:

| Aspect | Knowledge (`knowledge/`) | Data (`{workflow}/data/`) |
| --- | --- | --- |
| Scope | Cross-cutting, multi-workflow | Single workflow, single step |
| Content | Principles, patterns, judgment rules | Schemas, templates, scoring formulas |
| Index | `skf-knowledge-index.csv` | Referenced directly by step files |
| Examples | zero-hallucination, confidence-tiers | skill-brief-schema.md, scoring-rules.md |

**Knowledge files** live in `src/knowledge/` and capture principles Ferris applies across multiple workflows — zero hallucination, confidence tiers, provenance tracking, \[MANUAL\] preservation. Workflow steps reference these when they need cross-cutting judgment, not step-specific rules.

**Data files** live in each workflow's `data/` directory and contain operational artifacts tightly coupled to specific steps — schemas, templates, scoring formulas, extraction patterns.

Neither duplicates the other. Knowledge files reference (not repeat) data files where the detailed operational rules live.

## Directory Structure

Each workflow follows a consistent structure:

```
{workflow}/
├── workflow.md              # Entry point — goals, mode routing, step sequence
├── steps-c/                 # Create-mode steps (sequential execution)
│   ├── step-01-*.md
│   ├── step-02-*.md
│   └── ...
├── data/                    # Reference data — schemas, rules, patterns
│   └── *.md
└── templates/               # Output skeletons (only analyze-source, test-skill)
    └── *-template.md
```

### Step Loading

Steps execute sequentially via just-in-time loading. Only the current step is in context. Each step explicitly names the next step file. Data and template files are loaded on demand by the steps that need them.

## Workflow Details

### setup-forge (SF)

**5 steps** | **Data:** tier-rules.md

Detects available tools (ast-grep, gh, QMD), determines the capability tier (Quick/Forge/Forge+/Deep), writes `forge-tier.yaml` to the sidecar, and optionally indexes the project. Run this first — all other workflows adapt behavior to the detected tier.

### analyze-source (AN)

**7 steps** | **Data:** skill-brief-schema.md, unit-detection-heuristics.md | **Templates:** analysis-report-template.md

Brownfield onboarding entry point. Scans project structure, identifies skillable units using confidence-tiered heuristic signals, maps exports and integration points, presents recommendations for user confirmation, then generates `skill-brief.yaml` files ready for `create-skill --batch`.

### brief-skill (BS)

**5 steps** | **Data:** skill-brief-schema.md, scope-templates.md

Interactive guided discovery. Gathers user intent (target repo, language, what to skill), analyzes the target to understand boundaries, walks through scope definition with the user, confirms the brief, then writes a validated `skill-brief.yaml`.

### create-skill (CS)

**8 primary steps (11 step files including sub-steps)** | **Data:** extraction-patterns.md, extraction-patterns-tracing.md, skill-sections.md, tier-degradation-rules.md, compile-assembly-rules.md, source-resolution-protocols.md

The core compilation engine. Loads a brief, checks ecosystem context, extracts source with AST-backed provenance (T1 confidence when ast-grep available), enriches with usage patterns, compiles into agentskills.io-compliant sections, validates structural integrity, generates the `SKILL.md` artifact, and produces an evidence report. Supports `--batch` for processing multiple briefs.

### quick-skill (QS)

**6 steps** | **Data:** registry-resolution.md, skill-template.md

Fastest path to a skill. Accepts a GitHub URL or package name, resolves to source via registry lookup, performs ecosystem check, extracts public API surface without requiring a brief, compiles best-effort `SKILL.md`, validates, and writes output.

### create-stack-skill (SS)

**9 steps** | **Data:** integration-patterns.md, manifest-patterns.md, stack-skill-template.md, compose-mode-rules.md

Two modes: **Code-mode** analyzes dependency manifests and co-import patterns from actual source code. **Compose-mode** synthesizes a stack skill from pre-generated individual skills + architecture document (no codebase required). Both produce the same output format — consolidated stack skill with integration patterns.

### verify-stack (VS)

**6 steps** | **Data:** integration-verification-rules.md, coverage-patterns.md, feasibility-report-template.md

Pre-code verification engine. Cross-references generated skills against architecture and PRD documents. Three passes: coverage verification (does a skill exist for each tech?), integration verification (do the APIs actually connect?), and requirements verification (does the stack cover the PRD?). Produces a feasibility report with evidence-backed verdicts and prescriptive recommendations. Re-runnable — swap libraries, regenerate skills, re-verify.

### refine-architecture (RA)

**6 steps** | **Data:** refinement-rules.md

Architecture improvement engine. Takes the original architecture document and refines it using verified skill data and VS feasibility findings. Fills gaps, flags issues, suggests improvements — all backed by specific API evidence from the generated skills. Produces a refined architecture document.

### update-skill (US)

**7 steps** | **Data:** manual-section-rules.md, merge-conflict-rules.md, remote-source-resolution.md (tier-degradation-rules shared from create-skill)

Surgical update engine. Loads the existing skill, detects what changed in source since last compilation, re-extracts only affected exports with fresh provenance, merges new extractions while preserving all `[MANUAL]` developer-authored content, validates the merged result, writes the updated skill, and produces a change report.

### audit-skill (AS)

**6 steps** | **Data:** drift-report-template.md, severity-rules.md

Drift detection engine. Loads the skill under audit, re-indexes current source to build a fresh reference, performs structural diff (signature changes, missing exports), performs semantic diff (behavioral divergence), classifies each finding by severity using defined rules, and produces a graded drift report.

### test-skill (TS)

**7 steps** | **Data:** output-section-formats.md, scoring-rules.md, source-access-protocol.md | **Templates:** test-report-template.md

Quality gate before export. Loads the skill, detects test mode (naive for Quick tier, contextual for Forge/Deep), runs coverage checks against source, runs coherence checks for internal consistency, scores using weighted rubric, and produces a completeness report with pass/fail gate decision.

### export-skill (EX)

**6 steps** | **Data:** managed-section-format.md, snippet-format.md

Distribution packaging. Loads the completed skill, packages as agentskills.io-compliant bundle, generates context snippets optimized for token efficiency, updates managed sections in `CLAUDE.md` / `AGENTS.md` with platform-aware injection, produces a token budget report, and summarizes the export.
