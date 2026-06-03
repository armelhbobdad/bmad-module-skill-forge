---
title: Forge-Auto
description: Zero-ceremony skill creation — one command turns a GitHub repo, doc URL, or pinned version into a verified skill
---

Forge-Auto is a [pipeline alias](../workflows/#pipeline-aliases) that chains five workflows into a single command. Give it a repo URL, a documentation URL, or a pinned version, and it produces a verified skill in 3–5 minutes with zero configuration.

If you're new to SKF and want to try it without reading anything else, start here.

---

## Invocation

Three input types, one command pattern:

```
@Ferris forge-auto https://github.com/honojs/hono                  — repo URL
@Ferris forge-auto https://docs.example.com                         — doc URL (docs-only)
@Ferris forge-auto https://github.com/honojs/hono --pin v4.6.0      — pinned version
```

- **Repo URL** — analyzes the full source repository, extracts exports, and compiles a skill from code + docs.
- **Doc URL** — skips source analysis entirely and builds the skill from documentation alone. Useful for closed-source libraries or when the docs are the canonical reference.
- **`--pin <version>`** — targets a specific release. The version tag is resolved during analysis so the resulting skill is locked to that exact API surface.

---

## Pipeline Stages

forge-auto expands to `AN[auto] BS[auto] CS TS[min:90] EX`. The two analysis stages (AN, BS) run in [headless mode](../workflows/#headless-mode) via their `[auto]` flags — no confirmation gates, no interactive prompts. The compile, test, and export stages then proceed with their standard behaviors once the analysis context is ready.

| Stage | Workflow | Mode | What Happens |
|-------|----------|------|-------------|
| 1 | **Analyze Source** (AN) | `[auto]` | Scans the target, detects shape (`library-API`, `reference-app`, `language-reference`, `stack-compose`, or `unknown`), discovers exports, and generates a scope + brief automatically. |
| 2 | **Brief Skill** (BS) | `[auto]` | Enriches the auto-generated brief with doc detection results. No interactive scoping — the brief is assembled from AN's output. |
| 3 | **Create Skill** (CS) | standard | Compiles the skill from the enriched brief. Extracts exports, resolves documentation sources, validates structure. |
| 4 | **Test Skill** (TS) | `[min:90]` | Verifies completeness with a **90% quality threshold** (stricter than the default 80%). Fail halts the pipeline. |
| 5 | **Export Skill** (EX) | standard | Validates the package, generates context snippets, and injects into your IDE's context file. |

Data flows automatically between stages — the brief path from AN feeds BS, the skill name from CS feeds TS, and so on. See [Pipeline Mode](../workflows/#pipeline-mode) for the general mechanics.

---

## Automatic Behaviors

forge-auto's `[auto]` flags activate several behaviors that normally require manual input:

- **Auto-scope** — shape detection (`library-API`, `reference-app`, `language-reference`, `stack-compose`) drives scope decisions, mapping onto `scope.type` values like `full-library`, `public-api`, and `reference-app`. No interactive scope confirmation.
- **Auto-brief** — the brief is generated and enriched with doc-detection results in one pass, without the interactive discovery flow that `BS` uses standalone.
- **Coexistence detection** — if a skill for the same target already exists, forge-auto detects it and offers three options: create alongside (new version), merge into the existing skill, or skip.
- **Auto-decomposition** — multi-package monorepos (>3 packages) flag a *decomposition candidate*; a cohesion check then decides whether to merge into one cohesive skill (the usual outcome — published monorepos are mostly cohesive) or split into N. Exceeding 500 exports also flags a candidate. The default leans toward a single skill, not one-per-package.
- **Language-reference handling** — for compiler, interpreter, or parser repos, AN classifies the target as a `language-reference`. For a *whole-language* reference (a compiler/interpreter), the skill's value is the language's prose — the guide and standard-library docs — not compiler internals, so AN seeds the canonical corpora. If none are found it records an honest **DEGRADED** caveat: the skill is low-value as code-only until you attach the language's guide and std/library docs (re-run with a doc URL, or enrich via `US`).

---

## Expected Output

A successful forge-auto run produces a complete skill package in your forge data directory, exported and ready for use. The skill includes:

- `SKILL.md` — the compiled skill with provenance-cited instructions
- `metadata.json` — version, source, confidence tier breakdown
- Context snippet injected into your IDE context file (CLAUDE.md, .cursorrules, AGENTS.md, etc.)

The quality threshold is 90% — if the skill scores below that, the pipeline halts at TS with a gap report. Run `@Ferris US` to address gaps, then `@Ferris TS EX` to re-test and export.

---

## Timing

A typical library (50–200 exports) takes **3–5 minutes** end to end. Factors that increase time:

- Multi-package monorepos (>3 packages) flag a decomposition candidate; if the cohesion check splits the repo into N skills, add 1–3 minutes
- Doc-only targets depend on documentation site size and structure
- Deep-tier projects (with QMD and CCC) spend more time on enrichment

---

## Migration from `deepwiki` and `onboard`

This pipeline was briefly named `deepwiki`. It was renamed to **`forge-auto`** to avoid confusion with the [DeepWiki MCP](https://deepwiki.com) — `forge-auto` compiles a verified skill from source and **does not** call that MCP or ingest a generated wiki. `deepwiki` still works as a **deprecated alias** (it resolves to `forge-auto` and prints a one-time notice); prefer `forge-auto` going forward.

Before that, the auto pipeline replaced the older `onboard` alias. `onboard` has been removed — running it returns an error directing you to `forge-auto`. The key differences from `onboard`: it ran `AN CS TS EX` with standard (interactive) modes at an 80% quality threshold, whereas `forge-auto` adds auto-scope, auto-brief, a stricter quality gate (90% vs 80%), and accepts repo URLs and doc URLs — not just project paths.

---

## Related

- [Workflows](../workflows/) — pipeline mode mechanics, headless mode, circuit breakers
- [Concepts](../concepts/) — provenance, confidence tiers, drift, version pinning
- [BMAD Synergy](../bmad-synergy/) — how forge-auto fits into BMAD phases, and standalone SKF usage
