---
title: Concepts
description: Plain-English definitions of key Skill Forge terms — agent skills, provenance, confidence tiers, drift, and more
---

# Concepts

This page defines the key terms you'll encounter in Skill Forge. Each one is explained in plain English with a concrete example.

---

## Agent Skills

An agent skill is an instruction file that tells an AI agent how to use your code. Instead of the agent guessing your API from its training data, it reads the skill and gets real function names, real parameter types, and real usage patterns.

Skills follow the [agentskills.io](https://agentskills.io) open standard, so they work across Claude, Cursor, Copilot, and other AI tools.

**Example:** A skill for `better-auth` tells your agent: "The function is `authClient.signIn.email()`, it takes `{ email: string, password: string }`, and it returns a `Promise<Session>`. Here's the source: `src/client.ts:L47`."

---

## Provenance

Provenance means every instruction in a skill traces back to where it came from. For code, that's a file and line number. For documentation, it's a URL. For developer discourse, it's an issue or PR reference. If SKF can't point to a source, it doesn't include the instruction.

**Examples** (from a [real generated skill](https://github.com/armelhbobdad/oh-my-skills)):
- `[AST:cognee/api/v1/search/search.py:L26]` — extracted from source code via AST parsing
- `[SRC:cognee/api/v1/session/__init__.py:L8]` — read from source code without AST verification
- `[EXT:docs.cognee.ai/getting-started/quickstart]` — sourced from external documentation
- `[QMD:cognee-temporal:issues.md]` — surfaced from indexed developer discourse

---

## Confidence Tiers (T1/T2/T3)

Each piece of information in a skill carries a confidence level based on where it came from:

- **T1 — AST extraction:** Pulled directly from source code via AST parsing. This is structural truth — the function signature actually exists in the code right now.
- **T2 — Evidence:** Found in issues, PRs, changelogs, or documentation within the repository. Reliable context, but not as definitive as code.
- **T3 — External:** Pulled from external documentation or websites. Treated with caution and clearly marked.

**Example:** A function signature is T1. A deprecation warning from a closed GitHub issue is T2. A usage example from a blog post is T3.

---

## Capability Tiers (Quick/Forge/Deep)

Your capability tier depends on which tools you have installed. Each tier builds on the previous one:

- **Quick** — GitHub CLI only. SKF reads source files and builds best-effort skills. Works in under a minute.
- **Forge** — Adds [ast-grep](https://ast-grep.github.io). SKF uses AST parsing for structural truth. Instructions are verified against the actual code structure.
- **Deep** — Adds [QMD](https://github.com/tobi/qmd). SKF indexes knowledge for semantic search. Skills get enriched with historical context, deprecation warnings, and cross-reference intelligence.

You don't need all tools to start. SKF detects what you have and sets your tier automatically. See [How It Works](../architecture.md) for the full technical treatment.

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
