---
title: Examples
description: Real-world scenarios, tips, and troubleshooting for Skill Forge
---

# Examples & Use Cases

This section provides practical examples for using SKF: Skill Forge.

---

## Example Workflows

### Quick Skill — 47 Seconds

Developer adds `spacetimedb` to a Next.js project. Agent keeps hallucinating methods.

```
@Ferris QS spacetimedb
```

Ferris resolves to GitHub, extracts 14 public functions via source reading, validates against spec. Skill appears in `skills/spacetimedb/`. Agent stops hallucinating. Forty-seven seconds. Done.

### Brownfield Platform — 8 Minutes

Alex's team adopts BMAD for 10 microservices (TypeScript, Go, Rust).

```
@Ferris SF          # Setup — Deep mode detected
@Ferris AN          # Analyze — 10 services mapped
@Ferris CS --batch  # Create — batch generation
```

10 individual skills + 1 platform stack skill. BMM architect navigates cross-service flows with verified knowledge.

### Release Prep — Trust Builder

Sarah prepares v3.0.0 with breaking changes.

```
@Ferris AS    # Audit — finds 3 renames, 1 removal, 1 addition
@Ferris US    # Update — preserves [MANUAL] sections, adds annotations
@Ferris TS    # Test — verify completeness
@Ferris EX    # Export — package for npm release
```

Ships with npm release. Consumers upgrade — their agents use the correct function names. Zero hallucination tickets.

### Stack Skill — Integration Intelligence

Armel's full-stack project: Next.js + Serwist + SpacetimeDB + better-auth.

```
@Ferris SS
```

Ferris detects 8 significant dependencies, finds 5 co-import integration points. Generates a consolidated stack skill. The agent now knows: "When you modify the auth flow, update the Serwist cache exclusion at `src/sw.ts:L23`." Integration intelligence no other tool provides.

---

## Common Scenarios

### Scenario A: Greenfield + BMM Integration

BMAD user starts a new project. BMM architect suggests skill generation after retrospective.

```
@Ferris BS    # Brief — scope the skill
@Ferris CS    # Create — compile from brief
@Ferris TS    # Test — verify completeness
@Ferris EX    # Export — inject into CLAUDE.md
```

Skills accumulate over sprints. Agent gets smarter every iteration.

### Scenario B: Multi-Repo Platform

Alex needs cross-service knowledge for 10 microservices.

One forge project, multiple QMD collections, hub-and-spoke skills with integration patterns.

### Scenario C: External Dependency

Developer needs skills for a library that doesn't have official skills.

```
@Ferris QS better-auth
```

Checks ecosystem first. If no official skill exists: generates from source. `source_authority: community`.

### Scenario D: Docs-Only (SaaS/Closed Source)

No source code available — only documentation.

Generate from docs + QMD-indexed content. T2/T3 confidence only. `source_authority: community`.

---

## Tips & Tricks

### Progressive Capability

Start with Quick mode (no setup required), upgrade to Forge (install ast-grep), then Deep (QMD already included). Each tier builds on the previous — you never lose capability.

### Batch Operations

Use `--batch` with `create-skill` and `test-skill` to process multiple skills at once. Progress is checkpointed — use `--continue` to resume if interrupted.

### Stack Skills + Individual Skills

Stack skills focus on integration patterns. Individual skills focus on API surface. Use both together for maximum coverage.

### The Loop

After each sprint's refactor, run `@Ferris US` to regenerate changed components. Export updates CLAUDE.md automatically. Skill generation becomes routine — like running tests.

---

## Troubleshooting

### Common Issues

**"Forge halted: ast-grep not found"**
Install ast-grep to unlock Forge mode: <https://ast-grep.github.io>

**"No brief found"**
Run `@Ferris BS` first to create a skill brief, or use `@Ferris QS` for brief-less generation.

**"Ecosystem check: official skill exists"**
An official skill already exists for this package. Consider installing it with `npx skills add` instead of generating your own.

**Quick mode skills have lower confidence**
Quick mode reads source without AST analysis. Install ast-grep to upgrade to Forge mode for structural truth (T1 confidence).

---

## Getting More Help

- Run `@Ferris SF` to check your current tier and tool availability
- Review `forge-config.yaml` for runtime configuration
- Check module configuration in your BMAD settings
- Consult the broader BMAD documentation
