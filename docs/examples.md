---
title: Examples
description: Real-world scenarios and operational tips for Skill Forge. For common errors, see Troubleshooting.
---

## What the Output Looks Like

When SKF generates a skill, you get a `SKILL.md` file with machine-readable frontmatter and provenance-backed instructions. Below is a trimmed example from the real [`oms-cognee` SKILL.md](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/oms-cognee/1.0.0/oms-cognee/SKILL.md) generated for [cognee](https://github.com/topoteretes/cognee) (full portfolio at [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills)):

**Frontmatter (tells AI agents when to load this skill):**

```yaml
name: oms-cognee
description: >
  Builds apps on top of cognee v1.0.0, the knowledge-graph memory engine for AI agents.
  Use when ingesting text/files/URLs into persistent memory, building knowledge graphs,
  searching graph-backed memory with multiple SearchType modes, enriching graphs with
  memify/improve, scoping memory with datasets and node_sets, configuring LLM/embedding/
  graph/vector backends, running custom task pipelines, tracing operations, decorating
  agent entrypoints with `agent_memory`, connecting to Cognee Cloud with `serve`, or
  visualizing the graph. Covers cognee/__init__.py exports: the V1 API (add, cognify,
  search, memify, datasets, prune, update, run_custom_pipeline, config, SearchType,
  visualize_graph, pipelines, Drop, run_startup_migrations, tracing) and the V2
  memory-oriented API (remember, RememberResult, recall, improve, forget, serve,
  disconnect, visualize, agent_memory). Do NOT use for: cognee internals, the HTTP
  REST API (use cognee-mcp or the FastAPI server), non-cognee memory/RAG libraries.
```

**Body (what your AI agent reads):**

```
## Key API Summary

| Function | Purpose | Key Params | Source |
|----------|---------|------------|--------|
| add() | Ingest text, files, binary data | data, dataset_name | [AST:cognee/api/v1/add/add.py:L22] |
| cognify() | Build knowledge graph | datasets, graph_model | [AST:cognee/api/v1/cognify/cognify.py:L44] |
| search() | Query knowledge graph | query_text, query_type | [AST:cognee/api/v1/search/search.py:L27] |
| memify() | Enrich graph with custom tasks | extraction_tasks, data | [AST:cognee/modules/memify/memify.py:L25] |
| remember() | V2 one-shot memory ingest | data, dataset_name | [AST:cognee/api/v1/remember/remember.py:L339] |
| DataPoint | Base class for custom graph nodes | inherit and add fields | [EXT:docs.cognee.ai/guides/custom-data-models] |
```

Every line number above is copied from the real SKILL.md and points at the line where that function is defined in the cognee source, so none of it is illustrative. SKF also ships its extraction record for this skill in oh-my-skills: [`forge-data/oms-cognee/1.0.0/provenance-map.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.0.0/provenance-map.json).

Provenance tags trace each instruction to its source:
- `[AST:file:Lnn]` (T1): extracted from code via AST parsing (highest confidence)
- `[SRC:file:Lnn]` (T1-low): read from source code without AST verification
- `[QMD:collection:doc]` (T2): surfaced from indexed developer discourse (issues, PRs, changelogs)
- `[EXT:url]` (T3): sourced from external documentation (lowest confidence)

See [Skill Model → Output Architecture](/docs/skill-model.md#output-architecture) for the full output structure.

**Full skill directory structure** (real layout from [`oh-my-skills/skills/oms-cognee/`](https://github.com/armelhbobdad/oh-my-skills/tree/main/skills/oms-cognee)):

```
skills/oms-cognee/
├── active -> 1.0.0
├── 0.5.8/
│   └── oms-cognee/
│       ├── SKILL.md              # Archived: v0.5.8, pinned to b51dcce1
│       ├── context-snippet.md
│       ├── metadata.json
│       └── references/
└── 1.0.0/
    └── oms-cognee/
        ├── SKILL.md              # Active: pinned to cognee v1.0.0 (3c048aa4)
        ├── context-snippet.md    # Compressed index for platform context files
        ├── metadata.json         # Machine-readable provenance
        └── references/           # Progressive disclosure detail
            ├── config.md
            ├── core-workflow.md
            ├── full-api-reference.md
            └── pipelines-and-datapoints.md
```

This is the real directory listing from [`oh-my-skills/skills/oms-cognee/`](https://github.com/armelhbobdad/oh-my-skills/tree/main/skills/oms-cognee) after cognee shipped v1.0.0 upstream. SKF recompiled the skill from the v1.0.0 commit and wrote it next to the existing 0.5.8 tree. The older version stays pinned to its original commit (`b51dcce1`) and is still installable by any project that hasn't bumped its `CLAUDE.md` pin yet. The `active` symlink and the [`.export-manifest.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/.export-manifest.json) both point at the current version. Some skills also include `scripts/` and `assets/` directories when the source repository contains executable scripts or static assets. oms-cognee has neither; see [Skill Model → Per-Skill Output](/docs/skill-model.md#per-skill-output) for the full schema.

---

## Example Workflows

### Quick Skill: Under a minute

Developer adds [cognee](https://github.com/topoteretes/cognee) to a Python project for AI memory management. Agent keeps hallucinating method signatures and config options.

```
@Ferris QS https://github.com/topoteretes/cognee
```

Ferris reads the repository, lists its public exports, and validates against the agentskills.io spec. The skill is written to `skills/cognee/<version>/cognee/` (the version is detected from the source manifest). The agent now reads the real export names and usage examples from the skill instead of guessing. Quick Skill does not extract full signatures or cite a source line for each export. When you need those, run `@Ferris forge-auto https://github.com/topoteretes/cognee` instead.

Need a specific version? Append `@version`:

```
@Ferris QS cognee@1.0.0
```

### Brownfield Platform: Pipeline or per-workflow

Alex, a platform engineer, adopts BMAD for 10 microservices spanning TypeScript, Go, and Rust.

```
@Ferris SF                                              # Setup: Deep tier detected
# clear session
@Ferris forge-auto https://github.com/acme/auth-service   # one service per run: Analyze → Brief → Create → Test → Export
```

Or one workflow per session:
```
@Ferris SF          # Setup: Deep tier detected
# clear session
@Ferris AN          # Analyze: 10 services mapped
# clear session
@Ferris CS --batch  # Create: batch generation
# clear session
@Ferris SS          # Stack Skill: one platform skill for how the services connect
```

The result is 10 individual skills plus 1 platform stack skill, which SS builds once the individual skills exist. The [BMM](/docs/bmad-synergy.md#skf-and-bmm-phase-by-phase-playbook) architect then navigates cross-service flows using verified knowledge.

### Release Prep: Trust Builder

Jin, a Rust library maintainer, is preparing v1.0.0 with breaking changes she wants consumers' agents to pick up automatically.

```
@Ferris maintain cocoindex
```

Or one workflow per session:
```
@Ferris AS    # Audit: finds 3 renames, 1 removal, 1 addition
# clear session
@Ferris US    # Update: preserves [MANUAL] sections, adds annotations
# clear session
@Ferris TS    # Test: verify completeness
# clear session
@Ferris EX    # Export: package for distribution
```

Jin publishes the updated skill alongside the release (for an official skill, EX prints the `npx skills publish` command). Consumers upgrade and their agents use the correct function names, with no more "wrong signature" support tickets.

### Stack Skill: Integration Intelligence

Armel, building a full-stack side project on Next.js + Serwist + SpacetimeDB + better-auth.

```
@Ferris SS
```

Ferris detects 8 significant dependencies, finds 5 co-import integration points. Generates a consolidated stack skill. The agent now knows: "When you modify the auth flow, update the Serwist cache exclusion at `src/sw.ts:L23`." That integration detail isn't available from any other tool in the [comparison table](/docs/index.md#how-skf-compares).

### Pre-Code Architecture Verification: Greenfield Confidence

Gery, a backend architect, is designing a new TypeScript service on Hono + Drizzle + SpacetimeDB. The architecture doc is written but no code exists yet, and he wants to verify the stack holds together before anyone starts building.

```
@Ferris QS hono          # Quick Skill per library
@Ferris QS drizzle-orm
@Ferris QS spacetimedb-sdk
@Ferris VS               # Verify Stack: feasibility report
@Ferris RA               # Refine Architecture: enrich with API evidence
@Ferris SS               # Stack Skill: compose-mode (no codebase needed)
```

VS rates the Drizzle↔SpacetimeDB pair `Risky` (a query-model mismatch that a workaround may resolve) and returns an overall verdict of `CONDITIONALLY_FEASIBLE`. Gery adds a bridge layer to the architecture and re-runs VS, which now returns `FEASIBLE`. RA fills in verified API signatures. SS compose-mode builds the stack skill from the existing skills and the refined architecture. The agent now has integration intelligence for a project that doesn't have code yet.

---

## Common Scenarios

### Scenario A: Greenfield + BMM Integration

BMAD user starts a new project. [BMM](/docs/bmad-synergy.md#skf-and-bmm-phase-by-phase-playbook) architect suggests skill generation after retrospective.

```
@Ferris BS    # Brief: scope the skill
@Ferris CS    # Create: compile from brief
@Ferris TS    # Test: verify completeness
@Ferris EX    # Export: inject into platform context files
```

Skills accumulate over sprints. The agent's coverage improves each iteration.

### Scenario B: Multi-Repo Platform

Blondin, a platform lead, needs cross-service knowledge for 10 microservices so agents can navigate shared types and cross-calls.

```
@Ferris campaign    # Orchestrate all 10 skills across sessions, in dependency order
```

Campaign reads the dependencies you declare for each skill, orders the skills so each one comes after the skills it depends on, and drives each full-pipeline (Tier A) skill through analyze, brief, compile and test, with quality gates enforced. Libraries marked Tier B are built faster, in one Quick Skill batch. It then composes a capstone stack skill that shows how the services connect, and asks for your go-ahead before it exports anything. State is written to disk, so Blondin can walk away and run `@Ferris campaign resume` after the conversation runs out of context or after a break, picking up exactly where the last session stopped. See [Campaign Orchestration](/docs/campaign.md) for the full stage-by-stage flow.

### Scenario C: External Dependency

Kossi, a developer integrating an uncommon library, needs a skill for it, and nothing official exists yet.

```
@Ferris QS better-auth
```

Checks ecosystem first. If no official skill exists: generates from source. `source_authority: community`.

### Scenario D: Docs-Only (SaaS/Closed Source)

There is no source code to clone, only API documentation. Example: you're integrating the [Stripe API](https://docs.stripe.com/api) and want your agent to know the real endpoints, parameters, and error codes instead of hallucinating from training data.

```
@Ferris BS
# When asked for target, provide documentation URLs:
# https://docs.stripe.com/api/charges
# https://docs.stripe.com/api/payment_intents
# https://docs.stripe.com/api/errors
# Ferris sets source_type: "docs-only" and collects doc_urls
# When asked for target version, specify: 2025-04-30.basil
# Ferris confirms your doc URLs match that API version
@Ferris CS
# step 3 finds no source to extract; step 3c (Fetch Docs) downloads the doc pages
# All content is T3 [EXT:url] confidence. source_authority: community
```

The brief's `doc_urls` field drives the Fetch Docs step (step 3c). The agent uses whatever web fetching tool is available in its environment (Firecrawl, WebFetch, curl, etc.) to retrieve documentation as markdown and extract API information with `[EXT:url]` citations. No AST parsing is possible without source code, so every instruction carries T3 provenance (external documentation, the lowest confidence) instead of T1, and the skill is tagged `source_authority: community` regardless of tier.

### Scenario E: Rename a Skill

You generated a quick skill for `cognee` and now want a more specific name to distinguish it from the official one.

```
@Ferris RS
# Ferris asks: Which skill? → cognee
# Ferris asks: New name? → cognee-skf-community
# Ferris copies to new name across all versions, verifies every reference,
# updates the export manifest, rebuilds CLAUDE.md/AGENTS.md,
# then deletes the old name.
```

Transactional safety: if verification fails, the old skill stays intact.

### Scenario F: Drop a Deprecated Version

You have `cognee` with versions 0.1.0, 0.5.0, and 0.6.0 (active). Version 0.1.0 is obsolete.

```
@Ferris DS
# Ferris asks: Which skill? → cognee
# Ferris asks: Which version? → 0.1.0
# Ferris asks: Deprecate (keep files) or Purge (delete)? → Purge
# Ferris updates the manifest, rebuilds context files, deletes the 0.1.0 directory.
```

Version 0.6.0 remains active. Version 0.5.0 is untouched. The managed sections in CLAUDE.md/AGENTS.md no longer reference 0.1.0.

### Scenario G: Maximum Accuracy for a High-Stakes Library

You're building skills for a production payments library and need maximum citation density. Every signature must be AST-verified, and you want historical context (deprecations, migration notes) baked into the skill.

**Workflow:**

```
@Ferris SF
# Ferris detects installed tools and sets your tier automatically:
# - Quick: no tools required (best-effort, source-read only)
# - Forge: ast-grep (T1 AST-verified signatures)
# - Forge+: ast-grep + cocoindex-code (semantic pre-ranking for large repos)
# - Deep: ast-grep + gh + qmd (T2 evidence from issues, PRs, changelogs; cocoindex-code optional)
# Install the missing tools, then re-run @Ferris SF to promote your tier.
@Ferris BS    # Scope: confirm the forge tier is Deep (+ ccc if installed)
@Ferris CS    # Extract: AST + QMD enrichment
@Ferris TS    # Completeness score: 80%+ threshold
```

**What you get:** Every signature carries `[AST:file:Lnn]` at T1. Deprecation warnings and design rationale carry `[QMD:collection:doc]` at T2. Install tooling once, every downstream skill benefits. See [Capability Tiers](/docs/concepts.md#capability-tiers-quickforgeforgedeep).

### Scenario H: OSS Maintainer Publishing Official Skills

You maintain an OSS library and want to ship official agent skills alongside each release, distributed via [skills.sh](https://skills.sh) or [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills) so consumers install them with `npx skills add`.

**Workflow:**

```
@Ferris BS    # Scope the skill: set source_authority: official in the brief
@Ferris CS    # Compile: AST extraction + QMD enrichment (Deep tier recommended)
@Ferris TS    # Verify completeness before publishing (aim for 90%+; the pass line is 80%)
@Ferris EX    # Package for distribution: emits npx skills publish instructions
```

**What you get:** A verified skill pinned to the release commit, with `source_authority: official` surfaced in metadata as a trust signal so downstream tooling (and the ecosystem check in `@Ferris QS`) recognize it as maintainer-published rather than community-forged. Re-run `@Ferris maintain <skill>` (AS → US → TS → EX) on every release to keep published skills current.

---

## Tips & Tricks

### Skip Permissions for Faster Forging

> **Tip from Armel:** When forging skills with Claude Code, I run `claude --dangerously-skip-permissions` to bypass all permission prompts. SKF workflows read source code, clone remote repositories into `~/.skf/workspace/`, write skills to `skills/` and working files to `forge-data/`, keep their state in `_bmad/_memory/forger-sidecar/`, update the SKF section of CLAUDE.md, AGENTS.md or .cursorrules when you export, and call tools such as git, ast-grep, qmd, gh and npx. Every step is auditable in the [open source](https://github.com/armelhbobdad/bmad-module-skill-forge). Skipping permissions drastically reduces forge time: I start a pipeline, go [grab one of those coffees ☕ you keep offering](https://buymeacoffee.com/armelhbobdad), and come back to a completed workflow. Review the output at the end, not at every gate.

### Progressive Capability

Start with the Quick tier (no setup required). Install ast-grep to reach Forge. From there, add cocoindex-code for Forge+ (semantic discovery), or add the GitHub CLI (gh) and QMD for Deep (evidence from issues, PRs and changelogs). Deep does not need cocoindex-code, but it still uses it when installed, so adding a tool never takes a capability away. Re-run `@Ferris SF` after installing tools to update your tier.

### Batch Operations

Use `--batch` with `create-skill` to process multiple briefs at once. Progress is checkpointed per brief: if a batch is interrupted, re-run `@Ferris CS --batch` and Ferris resumes with the brief it was working on (that brief compiles again from the start).

### Stack Skills + Individual Skills

Stack skills focus on integration patterns. Individual skills focus on API surface. Use both together for maximum coverage.

### The Loop

After each sprint's refactor, run `@Ferris maintain <skill>` to audit, update, test and export the skill in one go. Update changes only the skill itself; Export is the step that refreshes the skill index in your platform context files (CLAUDE.md, AGENTS.md, .cursorrules). Skill generation becomes routine, like running tests.

### One Workflow Per Session

Clear your conversation context (start a new chat) before invoking a new workflow. Each SKF workflow loads step files, knowledge fragments, and extraction data into context. Starting fresh ensures the next workflow operates without interference from prior steps. A pipeline such as `forge-auto` or `maintain` counts as one invocation: Ferris chains its workflows for you. Sidecar state (forge tier, preferences) persists automatically across sessions, so you don't lose configuration.

### Full Control Over Scope

You can compile multiple skills from the same target (repo or docs) with different scopes and intents. Each brief defines what to extract and why, producing a distinct skill from the same source. For example, from a single library you could compile `cognee-core` for the public API, `cognee-graph-types` for the type system, and `cognee-migration` for upgrade patterns, each serving a different use case.

### Best Practices Built In

Generated skills automatically follow authoring best practices: third-person descriptions for reliable agent discovery, consistent terminology, degrees-of-freedom matching (prescriptive for fragile operations, flexible for creative tasks), and table-of-contents headers in large reference files. Discovery testing recommendations are included in test reports.

### Scripts & Assets

If your source repo includes executable scripts (such as `scripts/`, `bin/` or `tools/`) or static assets (such as `assets/`, `templates/` or `schemas/`), SKF detects and packages them automatically with provenance tracking. Scripts and assets you add yourself under `scripts/[MANUAL]/` or `assets/[MANUAL]/` are preserved during updates, just like `<!-- [MANUAL] -->` markers in SKILL.md.

### Let the Health Check Run

Every SKF workflow ends with a shared **health check** step where Ferris reflects on the session and lists any bugs, friction, or gaps it hit. With your approval, it files bugs as GitHub issues; friction and gaps go to a local queue in `forge-data/improvement-queue/` unless you also agree to file them. Clean runs end with a one-line all-clear and no extra work. When something breaks, it's SKF's primary feedback channel, so **please let workflows run to completion**. If you had to cancel before the health check fired, ask Ferris to run it (`@Ferris please run the workflow health check for this session`) or [open an issue directly](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). See [Workflow Health Check](/docs/workflows.md#terminal-step-health-check) for details.

---

## Something not working?

See [Troubleshooting](/docs/troubleshooting.md) for common errors (ast-grep unavailable, "no brief found", ecosystem check messages) and how to resolve them. For general setup help, see [Getting Started → Need help?](/docs/getting-started.md#need-help).
