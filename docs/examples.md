---
title: Examples
description: Real-world scenarios, tips, and troubleshooting for Skill Forge
---

# Examples & Use Cases

This section provides practical examples for using SKF: Skill Forge.

---

## Example Workflows

### Quick Skill — 47 Seconds

Developer adds [cognee](https://github.com/topoteretes/cognee) to a Python project for AI memory management. Agent keeps hallucinating method signatures and config options.

```
@Ferris QS https://github.com/topoteretes/cognee
```

Ferris reads the repository, extracts the public API via source reading, validates against spec. Skill appears in `skills/cognee/`. Agent stops hallucinating. Forty-seven seconds. Done.

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

```
@Ferris BS
# When asked for target, provide documentation URLs:
# https://docs.cognee.ai/
# Ferris sets source_type: "docs-only" and collects doc_urls
@Ferris CS
# step-03 skips (no source), step-03c fetches docs via doc_fetcher
# All content is T3 [EXT:url] confidence. source_authority: community
```

The brief's `doc_urls` field drives the doc_fetcher step. The agent uses whatever web fetching tool is available in its environment (Firecrawl, WebFetch, curl, etc.) to retrieve documentation as markdown and extract API information with T3 citations.

---

## Tips & Tricks

### Progressive Capability

Start with Quick mode (no setup required), upgrade to Forge (install ast-grep), then Deep (install QMD). Each tier builds on the previous — you never lose capability.

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

- Run `/bmad-help` — analyzes your current state and suggests what to do next
  (e.g. `/bmad-help my batch creation failed halfway, how do I resume?`)
  *Provided by the [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD) — not available in standalone SKF installations.*
- Run `@Ferris SF` to check your current tier and tool availability
- Review `forge-tier.yaml` in your forger sidecar for runtime configuration
- Check module configuration in your BMAD settings
