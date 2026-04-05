---
title: Workflows
description: All 14 SKF workflows with commands, steps, and connection diagram
---

# Workflows Reference

SKF has 14 workflows. You trigger them by typing commands to [Ferris](../agents/), the AI agent that runs everything. Each workflow handles a specific part of the skill lifecycle — from analyzing source code to packaging for distribution, plus management operations for renaming and dropping skills. If any terms are unfamiliar, see the [Concepts](../concepts/) page for definitions.

---

## Core Workflows

### Setup Forge (SF)

**Command:** `@Ferris SF`

**Purpose:** Initialize forge environment, detect tools (ast-grep, ccc, gh, qmd), set capability tier, index project in CCC (Forge+), verify QMD collection health (Deep).

**When to Use:** First time using SKF in a project. Run once per project.

**Key Steps:** Detect tools + Determine tier → CCC index check (Forge+) → Write forge-tier.yaml → QMD + CCC registry hygiene (Deep/Forge+) → Status report

**Agent:** Ferris (Architect mode)

---

### Brief Skill (BS)

**Command:** `@Ferris BS`

**Purpose:** Scope and design a skill through guided discovery.

**When to Use:** Before `Create Skill` when you want maximum control over what gets compiled.

**Key Steps:** Gather intent → Analyze target → Define scope → Confirm brief → Write skill-brief.yaml

**Agent:** Ferris (Architect mode)

---

### Create Skill (CS)

**Command:** `@Ferris CS`

**Purpose:** Compile a skill from a brief. Supports `--batch` for multiple briefs.

**When to Use:** After Brief Skill, or with an existing skill-brief.yaml.

**Key Steps:** Load brief → Ecosystem check → Extract (AST + scripts/assets) → QMD enrich (Deep) → Compile → Validate → Generate

**Agent:** Ferris (Architect mode)

---

### Update Skill (US)

**Command:** `@Ferris US`

**Purpose:** Smart regeneration preserving `[MANUAL]` sections. Detects individual vs stack internally.

**When to Use:** After source code changes when an existing skill needs updating.

**Key Steps:** Load existing → Detect changes (incl. scripts/assets) → Re-extract → Merge (preserve MANUAL) → Validate → Write → Report

**Agent:** Ferris (Surgeon mode)

---

## Feature Workflows

### Quick Skill (QS)

**Command:** `@Ferris QS <package-or-url>` or `@Ferris QS <package-or-url>@<version>`

**Purpose:** Brief-less fast skill with package-to-repo resolution.

**When to Use:** When you need a skill quickly — no brief needed. Accepts package names or GitHub URLs. Append `@version` to target a specific version (e.g., `@Ferris QS cognee@0.5.0`).

**Key Steps:** Resolve target → Ecosystem check → Quick extract → Compile → Validate → Write

**Agent:** Ferris (Architect mode)

---

### Stack Skill (SS)

**Command:** `@Ferris SS`

**Purpose:** Consolidated project stack skill with integration patterns. Supports two modes: **code-mode** (analyzes a codebase) and **compose-mode** (synthesizes from existing skills + architecture document, no codebase required).

**When to Use:** When you want your agent to understand your entire project stack — not just individual libraries. Use code-mode for existing projects; compose-mode activates automatically after the VS → RA verification path when skills exist but no codebase is present.

**Key Steps (code-mode):** Detect manifests → Rank dependencies → Scope confirmation → Parallel extract → Detect integrations → Compile stack → Generate references

**Key Steps (compose-mode):** Load existing skills → Confirm scope → Detect integrations from architecture doc → Compile stack → Generate references

**Agent:** Ferris (Architect mode)

---

### Analyze Source (AN)

**Command:** `@Ferris AN`

**Purpose:** Decomposition engine — discover what to skill, recommend stack skill.

**When to Use:** Brownfield onboarding of large repos or multi-service projects.

**Key Steps:** Init → Scan project → Identify units → Map exports & detect integrations → Recommend → Generate briefs

**Note:** Supports resume — if the session is interrupted mid-analysis, re-run `@Ferris AN` and Ferris will resume from where it left off.

**Agent:** Ferris (Architect mode)

---

### Audit Skill (AS)

**Command:** `@Ferris AS`

**Purpose:** Drift detection between skill and current source.

**When to Use:** To check if a skill has fallen out of date with its source code.

**Key Steps:** Load skill → Re-index source → Structural diff (incl. script/asset drift) → Semantic diff (Deep) → Classify severity → Report

**Agent:** Ferris (Audit mode)

---

### Test Skill (TS)

**Command:** `@Ferris TS`

**Purpose:** Cognitive completeness verification. Naive and contextual modes. Quality gate before export.

**When to Use:** After creating or updating a skill, before exporting.

**Key Steps:** Load skill → Detect mode → Coverage check → Coherence check → External validation (skill-check, tessl) → Score → Gap report

**Scored Categories:** Export Coverage (36%), Signature Accuracy (22%), Type Coverage (14%), Coherence (18%), External Validation (10%). Default pass threshold: **80%**. Pass routes to Export Skill; fail routes to Update Skill with a gap report. See [Completeness Scoring](../how-it-works/#completeness-scoring) for the full formula and tier adjustments.

**Agent:** Ferris (Audit mode)

---

## Architecture Verification Workflows

### Verify Stack (VS)

**Command:** `@Ferris VS`

**Purpose:** Pre-code stack feasibility verification. Cross-references generated skills against architecture and PRD documents with three passes: coverage, integration compatibility, and requirements.

**When to Use:** After generating individual skills with CS/QS, before building a stack skill — to verify the tech stack can support the architecture.

**Key Steps:** Load skills + docs → Coverage analysis → Integration verification → Requirements check → Synthesize verdict → Present report

**Agent:** Ferris (Audit mode)

---

### Refine Architecture (RA)

**Command:** `@Ferris RA`

**Purpose:** Evidence-backed architecture improvement. Takes the original architecture doc + generated skills + optional VS report, fills gaps, flags contradictions, and suggests improvements — all citing specific APIs.

**When to Use:** After VS confirms feasibility, before running SS in compose-mode. Produces a refined architecture ready for stack skill composition.

**Key Steps:** Load inputs → Gap analysis → Issue detection → Improvement detection → Compile refined doc → Present report

**Agent:** Ferris (Architect mode)

---

## Utility Workflows

### Export Skill (EX)

**Command:** `@Ferris EX`

**Purpose:** Validate package structure, generate context snippets, and inject managed sections into CLAUDE.md/AGENTS.md/.cursorrules.

**When to Use:** When a skill is ready for CLAUDE.md/AGENTS.md integration. Also provides distribution instructions for `npx skills publish`.

**Key Steps:** Load skill → Validate package → Generate snippet → Update context file (CLAUDE.md/AGENTS.md/.cursorrules) → Token report → Summary

**Agent:** Ferris (Delivery mode)

---

## Management Workflows

### Rename Skill (RS)

**Command:** `@Ferris RS`

**Purpose:** Rename a skill across all its versions. Because the agentskills.io spec requires `name` to match parent directory name, this is a coordinated move across outer/inner directories, SKILL.md frontmatter, metadata.json, context snippets, provenance maps, the export manifest, and platform context files.

**When to Use:** You need to change a skill's name — for example, graduating a `QS`-generated skill (named from the repo) to a formal name, or adding a suffix like `-community` to distinguish from an official skill.

**Key Steps:** Select skill + new name → Transactional copy → Update all references → Rebuild context files → Delete old name (point of no return)

**Safety:** Transactional — if any step fails before the final delete, the old skill remains intact. Warns if `source_authority: "official"` (rename is local-only; published registry skill won't change).

**Agent:** Ferris (Management mode)

---

### Drop Skill (DS)

**Command:** `@Ferris DS`

**Purpose:** Drop a specific skill version or an entire skill. Soft drop (default) marks the version as deprecated in the manifest and keeps files on disk. Hard drop (`--purge`) also deletes the files.

**When to Use:** Retire a deprecated version (e.g., drop `cognee 0.1.0` because it's obsolete), free disk space, or remove a skill you no longer need.

**Key Steps:** Select skill → Select version(s) + mode → Update manifest → Rebuild context files → Delete files (if purge)

**Safety:** Active version guard — cannot drop the currently active version when other non-deprecated versions exist (switch active first, or drop all). Soft drop is reversible by editing the manifest.

**Agent:** Ferris (Management mode)

---

## Workflow Connections

**Standard path (code-mode):**

```mermaid
flowchart TD
    SF[Setup Forge — one-time] --> AN[Analyze Source]
    SF --> QS[Quick Skill]
    SF --> SS_code[Stack Skill — code-mode]

    AN --> BS[Brief Skill]
    BS --> CS[Create Skill]
    AN -->|direct| CS

    CS --> TS[Test Skill — quality gate]
    QS --> TS
    SS_code --> TS

    TS --> EX[Export Skill]
    TS --> AS[Audit Skill]
    AS --> US[Update Skill]
    US --> TS
```

**Pre-code verification path (compose-mode):**

```mermaid
flowchart TD
    GEN["Create Skill | Quick Skill ×N<br/>(per library)"] --> VS[Verify Stack — feasibility report]
    VS --> RA[Refine Architecture — refined doc]
    RA --> SS_compose[Stack Skill — compose-mode]
    SS_compose --> TS[Test Skill]
    TS --> EX[Export Skill]
```

> **One workflow per session.** Each arrow in the diagrams above represents a new conversation session. Clear your context between workflows for best results — this prevents leftover step files and extraction data from interfering with the next workflow. See [Session Context](../concepts/#session-context).

---

## Workflow Categories

| Category | Workflows | Description |
|----------|-----------|-------------|
| Core | SF, BS, CS, US | Setup, brief, create, and update skills |
| Feature | QS, SS, AN | Quick skill, stack skill, and analyze source |
| Quality | AS, TS | Audit skill completeness and test skill accuracy |
| Architecture Verification | VS, RA | Pre-code architecture feasibility and refinement |
| Utility | EX | Package and export for consumption |
| In-Agent | WS, KI | WS: show lifecycle position, active briefs, and forge tier; KI: list knowledge fragments (both in-agent, no file-based workflow) |
