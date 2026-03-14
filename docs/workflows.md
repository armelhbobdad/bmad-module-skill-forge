---
title: Workflows
description: All 10 SKF workflows with commands, steps, and connection diagram
---

# Workflows Reference

SKF includes 10 workflows organized by purpose:

---

## Core Workflows

### Setup Forge (SF)

**Command:** `@Ferris SF`

**Purpose:** Initialize forge environment, detect tools, set capability tier, verify QMD collection health.

**When to Use:** First time using SKF in a project. Run once per project.

**Key Steps:** Detect tools → Determine tier → Write forge-tier.yaml → QMD hygiene (Deep)

**Agent:** Ferris (Architect mode)

---

### Brief Skill (BS)

**Command:** `@Ferris BS`

**Purpose:** Scope and design a skill through guided discovery.

**When to Use:** Before `Create Skill` when you want maximum control over what gets compiled.

**Key Steps:** Gather intent → Analyze target → Define scope → Write skill-brief.yaml

**Agent:** Ferris (Architect mode)

---

### Create Skill (CS)

**Command:** `@Ferris CS`

**Purpose:** Compile a skill from a brief. Supports `--batch` for multiple briefs.

**When to Use:** After Brief Skill, or with an existing skill-brief.yaml.

**Key Steps:** Load brief → Ecosystem check → AST extract → QMD enrich → Compile → Validate → Generate

**Agent:** Ferris (Architect mode)

---

### Update Skill (US)

**Command:** `@Ferris US`

**Purpose:** Smart regeneration preserving `[MANUAL]` sections. Detects individual vs stack internally.

**When to Use:** After source code changes when an existing skill needs updating.

**Key Steps:** Load existing → Detect changes → Re-extract → Merge (preserve MANUAL) → Validate → Write

**Agent:** Ferris (Surgeon mode)

---

## Feature Workflows

### Quick Skill (QS)

**Command:** `@Ferris QS <package-or-url>`

**Purpose:** Brief-less fast skill with package-to-repo resolution.

**When to Use:** When you need a skill quickly — no brief needed. Accepts package names or GitHub URLs.

**Key Steps:** Resolve target → Ecosystem check → Quick extract → Compile → Validate → Write

**Agent:** Ferris (Architect mode)

---

### Stack Skill (SS)

**Command:** `@Ferris SS`

**Purpose:** Consolidated project stack skill with integration patterns.

**When to Use:** When you want your agent to understand your entire project stack — not just individual libraries.

**Key Steps:** Detect manifests → Rank dependencies → Scope confirmation → Parallel extract → Detect integrations → Compile stack → Generate references

**Agent:** Ferris (Architect mode)

---

### Analyze Source (AN)

**Command:** `@Ferris AN`

**Purpose:** Decomposition engine — discover what to skill, recommend stack skill.

**When to Use:** Brownfield onboarding of large repos or multi-service projects.

**Key Steps:** Scan project → Identify units → Map exports → Detect integrations → Recommend → Generate briefs

**Agent:** Ferris (Architect mode)

---

### Audit Skill (AS)

**Command:** `@Ferris AS`

**Purpose:** Drift detection between skill and current source.

**When to Use:** To check if a skill has fallen out of date with its source code.

**Key Steps:** Load skill → Re-index source → Structural diff → Semantic diff (Deep) → Classify severity → Report

**Agent:** Ferris (Audit mode)

---

### Test Skill (TS)

**Command:** `@Ferris TS`

**Purpose:** Cognitive completeness verification. Quality gate before export.

**When to Use:** After creating or updating a skill, before exporting.

**Key Steps:** Load skill → Detect mode → Coverage check → Coherence check → Score → Gap report

**Agent:** Ferris (Audit mode)

---

## Utility Workflows

### Export Skill (EX)

**Command:** `@Ferris EX`

**Purpose:** Package for distribution + platform-aware context injection into CLAUDE.md/AGENTS.md.

**When to Use:** When a skill is ready for distribution or CLAUDE.md integration.

**Key Steps:** Load skill → Package → Generate snippet → Update CLAUDE.md → Token report → Summary

**Agent:** Ferris (Delivery mode)

---

## Workflow Connections

```
                    setup-forge (one-time)
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     analyze-source  quick-skill  create-stack-skill
          │              │              │
     brief-skill         │              │
          │              │              │
     create-skill        │              │
          │              │              │
          └──────┬───────┘──────────────┘
                 │
            test-skill (quality gate)
                 │
          ┌──────┼──────┐
          │             │
     export-skill  audit-skill
                        │
                   update-skill (loops back to test)
```

---

## Build Priority

| Phase | Workflows | Notes |
|-------|-----------|-------|
| 1a (Core Engine) | setup-forge, create-skill, test-skill, export-skill | Must build first |
| 1b (Entry Points) | quick-skill, brief-skill, create-stack-skill | Complete v1.0 |
| 2 (Lifecycle) | audit-skill, update-skill, analyze-source | Post-launch |
