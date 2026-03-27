---
title: Examples
description: Real-world scenarios, tips, and troubleshooting for Skill Forge
---

# Examples & Use Cases

This section provides practical examples for using SKF: Skill Forge.

---

## What the Output Looks Like

When SKF generates a skill, you get a `SKILL.md` file with machine-readable frontmatter and provenance-backed instructions. Here's a trimmed example from a real skill generated for [cognee](https://github.com/topoteretes/cognee) (browse the full output at [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills)):

**Frontmatter (tells AI agents when to load this skill):**

```yaml
name: cognee
description: Use when cognee is a Python AI memory engine that transforms
  documents into knowledge graphs with vector and graph storage for semantic
  search and reasoning. Use this skill when writing code that calls cognee's
  Python API (add, cognify, search, memify, config, datasets, prune, session).
```

**Body (what your AI agent reads):**

```
## Key API Summary

| Function | Purpose | Key Params | Source |
|----------|---------|------------|--------|
| add() | Ingest text, files, binary data | data, dataset_name | [AST:cognee/api/v1/add/add.py:L22] |
| cognify() | Build knowledge graph | datasets, graph_model | [AST:cognee/api/v1/cognify/cognify.py:L47] |
| search() | Query knowledge graph | query_text, query_type | [AST:cognee/api/v1/search/search.py:L26] |
| memify() | Enrich graph with custom tasks | extraction_tasks, data | [AST:cognee/modules/memify/memify.py:L27] |
| session.* | Session history and feedback | get_session(), add_feedback() | [SRC:cognee/api/v1/session/__init__.py:L8] |
| DataPoint | Base class for custom graph nodes | inherit and add fields | [EXT:docs.cognee.ai/guides/custom-data-models] |
```

Provenance tags trace each instruction to its source:
- `[AST:file:line]` — extracted from code via AST parsing (highest confidence)
- `[SRC:file:line]` — read from source code without AST verification
- `[EXT:url]` — sourced from external documentation
- `[QMD:collection:doc]` — surfaced from indexed developer discourse (issues, PRs, changelogs)

See [How It Works](../how-it-works/) for the full output structure.

**Full skill directory structure:**

```
skills/cognee/
├── SKILL.md              # What your agent reads
├── context-snippet.md    # Compressed index for CLAUDE.md
├── metadata.json         # Machine-readable provenance
├── references/           # Progressive disclosure detail
│   ├── api-core.md
│   └── graph-types.md
├── scripts/              # Executable utilities (when detected)
│   └── setup-graphdb.sh
└── assets/               # Templates and schemas (when detected)
    └── config-schema.json
```

The `scripts/` and `assets/` directories appear only when the source repository contains them. Each file traces back to its source with provenance citations and SHA-256 hashes.

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

### Pre-Code Architecture Verification — Greenfield Confidence

Jordan is designing a new TypeScript backend with Hono + Drizzle + SpacetimeDB. Architecture doc written, but no code yet. Wants to verify the stack works before building.

```
@Ferris QS hono          # Quick Skill per library
@Ferris QS drizzle-orm
@Ferris QS spacetimedb-sdk
@Ferris VS               # Verify Stack — feasibility report
@Ferris RA               # Refine Architecture — enrich with API evidence
@Ferris SS               # Stack Skill — compose-mode (no codebase needed)
```

VS finds a Risky integration between Drizzle and SpacetimeDB (incompatible query models) and returns CONDITIONALLY FEASIBLE. Jordan adds a bridge layer to the architecture, re-runs VS → FEASIBLE. RA fills in verified API signatures. SS compose-mode synthesizes the stack skill from existing skills + refined architecture. The agent now has integration intelligence for a project that doesn't have code yet.

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

Start with Quick mode (no setup required), upgrade to Forge (install ast-grep), then Forge+ (install cocoindex-code for semantic discovery), then Deep (install QMD). Each tier builds on the previous — you never lose capability.

### Batch Operations

Use `--batch` with `create-skill` to process multiple briefs at once. Progress is checkpointed — if interrupted, re-run `@Ferris CS --batch` and Ferris will resume automatically from where it left off.

### Stack Skills + Individual Skills

Stack skills focus on integration patterns. Individual skills focus on API surface. Use both together for maximum coverage.

### The Loop

After each sprint's refactor, run `@Ferris US` to regenerate changed components. Export updates CLAUDE.md automatically. Skill generation becomes routine — like running tests.

### Best Practices Built In

Generated skills automatically follow authoring best practices: third-person descriptions for reliable agent discovery, consistent terminology, degrees-of-freedom matching (prescriptive for fragile operations, flexible for creative tasks), and table-of-contents headers in large reference files. Discovery testing recommendations are included in test reports.

### Scripts & Assets

If your source repo includes executable scripts (`scripts/`, `bin/`) or static assets (`templates/`, `schemas/`), SKF detects and packages them automatically with provenance tracking. Custom scripts you add to `scripts/[MANUAL]/` are preserved during updates — just like `<!-- [MANUAL] -->` markers in SKILL.md.

---

## Troubleshooting

### Common Issues

**Forge reports ast-grep is unavailable**
If setup-forge reports that ast-grep was not detected, install it to unlock Forge mode: <https://ast-grep.github.io>

**"No brief found"**
Run `@Ferris BS` first to create a skill brief, or use `@Ferris QS` for brief-less generation.

**"Ecosystem check: official skill exists"**
An official skill already exists for this package. Consider installing it with `npx skills add` instead of generating your own.

**Quick mode skills have lower confidence**
Quick mode reads source without AST analysis. Install ast-grep to upgrade to Forge mode for structural truth (T1 confidence).

**Want semantic discovery for large codebases?**
Install [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) to unlock Forge+ mode. CCC indexes your codebase and pre-ranks files by semantic relevance before AST extraction, improving coverage on projects with 500+ files.

---

## Getting More Help

- Run `/bmad-help` — analyzes your current state and suggests what to do next
  (e.g. `/bmad-help my batch creation failed halfway, how do I resume?`)
  *Provided by the [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD) — not available in standalone SKF installations.*
- Run `@Ferris SF` to check your current tier and tool availability
- Review `forge-tier.yaml` in your forger sidecar for runtime configuration
- Check module configuration in your BMAD settings
