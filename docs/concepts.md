---
title: Concepts
description: Plain-English definitions of key Skill Forge terms — agent skills, provenance, confidence tiers, drift, and more
---

# Concepts

This page defines the key terms you'll encounter in Skill Forge, with concrete examples.

---

## Agent Skills

An agent skill is an instruction file that tells an AI agent how to use your code. Instead of the agent guessing your API from its training data, it reads the skill and gets real function names, real parameter types, and real usage patterns.

Skills follow the [agentskills.io](https://agentskills.io) open standard, so they work across Claude, Cursor, Copilot, and other AI tools.

**Example:** A skill for [cognee](https://github.com/armelhbobdad/oh-my-skills) tells your agent: "The function is `cognee.search()`, it takes `query_text`, `query_type`, `top_k`, and `session_id`, and it's defined at `cognee/api/v1/search/search.py:L26`." Every parameter and location is AST-verified from the actual source code.

---

## Provenance

Provenance means every instruction in a skill traces back to where it came from. For code, that's a file and line number. For documentation, it's a URL. For developer discourse, it's an issue or PR reference. If SKF can't point to a source, it doesn't include the instruction.

**Examples** (from a [real generated skill](https://github.com/armelhbobdad/oh-my-skills)):
- `[AST:cognee/api/v1/search/search.py:L26]` — extracted from source code via AST parsing (T1)
- `[SRC:cognee/api/v1/session/__init__.py:L8]` — read from source code without AST verification (T1-low)
- `[QMD:cognee-temporal:issues.md]` — surfaced from indexed developer discourse (T2)
- `[EXT:docs.cognee.ai/getting-started/quickstart]` — sourced from external documentation (T3)

---

## Confidence Tiers (T1/T1-low/T2/T3)

Each piece of information in a skill carries a confidence level based on where it came from:

- **T1 — AST extraction:** Pulled directly from source code via AST parsing. This is structural truth — the function signature actually exists in the code right now. Cited as `[AST:file:Lnn]`.
- **T1-low — Source reading:** Found by reading source files directly without AST parsing. The location is correct but the type signature may be inferred. Produced by Quick tier and by Forge/Forge+/Deep when ast-grep cannot parse a specific file. Cited as `[SRC:file:Lnn]`.
- **T2 — Evidence (Deep tier only):** Surfaced by QMD knowledge search from issues, PRs, changelogs, or documentation within the repository. Available only when QMD is installed (Deep tier). Reliable context, but not as definitive as code. Cited as `[QMD:collection:document]`. T2 has two temporal subtypes:
  - **T2-past** — Historical context (closed issues, merged PRs, changelogs) explaining API design decisions. Surfaces in the skill's `references/` directory.
  - **T2-future** — Forward-looking context (open PRs, deprecation warnings, RFCs) about upcoming changes. Surfaces in SKILL.md Section 4b (Migration & Deprecation Warnings) and `references/`.
- **T3 — External:** Pulled from external documentation or websites. Treated with caution and clearly marked. Cited as `[EXT:url]`.

Forge+ semantic discovery (via cocoindex-code) does not introduce a new confidence tier — it influences *which* files are extracted, not *how* they're cited. Discovered files are verified by ast-grep (T1) or source reading (T1-low).

See the [Provenance](#provenance) examples above for real citations at each tier.

---

## Capability Tiers (Quick/Forge/Forge+/Deep)

Your capability tier depends on which tools you have installed. Each tier builds on the previous one:

- **Quick** — No tools required. SKF reads source files and builds best-effort skills. Works in under a minute. GitHub CLI used when available.
- **Forge** — Adds [ast-grep](https://ast-grep.github.io). SKF uses AST parsing for structural truth. Instructions are verified against the actual code structure.
- **Forge+** — Adds [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code). SKF uses semantic code search to discover relevant source regions before AST extraction, improving coverage on large codebases.
- **Deep** — Full pipeline: requires [ast-grep](https://ast-grep.github.io) + [GitHub CLI](https://cli.github.com) + [QMD](https://github.com/tobi/qmd) (all three). SKF indexes knowledge for semantic search and performs GitHub repository exploration. Skills get enriched with historical context, deprecation warnings, and cross-reference intelligence. CCC (cocoindex-code) enhances Deep tier when installed — ast-grep + gh + qmd + ccc gives maximum capability.

You don't need all tools to start. SKF detects what you have and sets your tier automatically. See [How It Works](../how-it-works/) for the full technical treatment.

---

## Drift

Drift happens when the source code changes but the skill instructions haven't been updated to match. A skill might still reference a function that was renamed, removed, or had its signature changed.

SKF detects drift by comparing the skill's recorded provenance against the current code. The `audit-skill` workflow (`@Ferris AS`) scans for these mismatches.

**Example:** Your skill says `createUser(name: string)` but the function was renamed to `registerUser(name: string, email: string)` in the last release. That's drift.

---

## Version Pinning

Every skill records the exact version (or commit) of the source code it was built from. This means you always know which version of the library the instructions apply to.

When the source updates, you can re-run `@Ferris US` (update-skill) to regenerate the skill for the new version while preserving any manual additions you've made.

---

## BMAD Module

SKF is a plugin (called a "module") for the [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD), a framework for running structured AI workflows. BMad provides the workflow engine — step-by-step execution, shared knowledge bases, and consistent outputs. SKF plugs into that engine and focuses specifically on skill compilation.

You don't need to know BMad to use SKF. The standalone installer sets everything up.

---

## Ferris

Ferris is the AI agent persona that runs all SKF workflows. When you type `@Ferris CS`, you're telling Ferris to run the create-skill workflow.

Ferris switches between four modes depending on which workflow is active: Architect (exploring and building), Surgeon (precise updates), Audit (quality checks), and Delivery (packaging for distribution).

---

## Zero Hallucination

SKF's core principle: if an instruction can't be traced back to actual source code, it doesn't get included in the skill. This is the opposite of how most AI tools work — they generate plausible-sounding content from training data. SKF only includes what it can verify.

This doesn't mean skills are perfect. Quick-tier skills read source files without AST verification, so they rely on best-effort extraction. But even Quick skills cite their sources, and no tier includes invented information.

---

## Scripts & Assets

Skills can include executable scripts and static assets alongside the main SKILL.md instructions. Scripts handle deterministic operations (validation, setup, data processing) while assets provide templates, schemas, and configuration examples. Both are extracted from the source repository with provenance tracking — SKF copies them, it doesn't fabricate them.

**Example:** A database library skill might include `scripts/migrate.sh` (copied from the library's `bin/` directory) and `assets/config-schema.json` (copied from the library's `schemas/` directory). Each file carries a `[SRC:file:L1]` citation and SHA-256 hash for drift detection.

---

## Best Practices

SKF integrates skill authoring best practices from the Claude platform and community guidelines. Generated skills use third-person descriptions for reliable agent discovery, consistent terminology throughout, and appropriate degrees of freedom (prescriptive for fragile operations like database migrations, flexible for creative tasks like code reviews). These practices are enforced during compilation and verified during testing.

**Example:** A skill description reads "Processes payments via REST API with token-based auth. NOT for: billing dashboards" — third-person voice, specific keywords, and negative triggers help agents select the right skill.
