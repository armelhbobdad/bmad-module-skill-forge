---
title: Why Skill Forge?
description: The strategic case for SKF, covering the problem it solves, how it compares to alternatives, who it's for, and who it isn't.
---

Skill Forge compiles AI skills where each claim your agent reads points back to a real upstream location: a `file:line` at a pinned commit when source is available, or a documentation URL when it isn't. Not "sourced from training data." Not "retrieved from context." **Cited.** You can open the upstream repo (or the doc page) and see the function exists in under a minute. That is the core idea. This page explains why it matters, how SKF compares to alternatives, and who it's for.

---

## The problem you're hiring SKF to solve

Your AI agents read your codebase through the lens of whatever happened to be in their training data. When that training data is wrong, stale, or incomplete, your agent invents: function names that don't exist, parameter types that don't match, config options removed two versions ago. You catch some of it in review. You ship some of it by accident. Every sprint, your team spends hours untangling code that only compiles in the AI's imagination.

SKF treats this as a citation problem, not a model problem. If a skill claims `cognee.search()` takes `query_text` as its first parameter, SKF points to `cognee/api/v1/search/search.py:L27` at commit `3c048aa4` in the upstream repo. That's the whole pitch: **nothing is made up, and everything is falsifiable in 60 seconds.**

---

## How SKF compares

<div class="comparison-table">

| Approach | What it does well | Where it falls short |
|----------|-------------------|----------------------|
| Skill scaffolding (`npx skills init`) | Creates a SKILL.md template in the standard skill format | The template holds only placeholder text, so you still write every instruction by hand |
| LLM summarization | Understands context and intent | Generates plausible-sounding content that may not match the actual API |
| RAG (retrieval) or pasting code into the prompt | Finds relevant code snippets | Hands over loose fragments, not a finished skill your agent can follow |
| Manual authoring | High initial accuracy | Drifts as the source code changes, doesn't scale across dependencies |
| IDE built-in context (Copilot, Cursor) | Convenient, zero setup | Uses generic training data, not your project's specific integration patterns |
| **Skill Forge** | **Every instruction cites upstream: a source file and line at a pinned commit for source skills, a doc URL for docs-only skills. Falsifiable in 60 seconds.** | **Coverage depends on which tools you've installed, which set your capability tier (Quick / Forge / Forge+ / Deep). Quick Skill (QS) makes a best-effort skill with no provenance map.** |

</div>

---

## What "falsifiable in 60 seconds" actually means

Pick any symbol in any SKF-compiled skill. Three clicks:

1. Open the skill's `metadata.json`: it names the upstream repo (`source_repo`) and the exact commit (`source_commit`).
2. Open `provenance-map.json` in the skill's forge folder (`forge-data/{skill}/{version}/`, next to its test report) and find your symbol: it lists the file and line.
3. Visit the upstream repo at that commit and that line. The signature in the skill should match.

For docs-only skills, the audit shape is the same, with two differences: `metadata.json` records no commit, and the entries in `provenance-map.json` cite `[EXT:{url}]` instead of a file and line. Step 3 becomes "open the doc URL and confirm the signature matches."

If it doesn't, **that's a bug.** For a skill from oh-my-skills, [open an issue there](https://github.com/armelhbobdad/oh-my-skills/issues) with the file and line. The fix ships publicly with a new commit SHA and a new provenance map. If a skill you compiled with SKF gets it wrong, [open a bug report](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) on SKF. SKF treats any disagreement between claim and source as a defect.

Quick Skill (QS) is the exception. It makes a fast, best-effort skill with a `metadata.json` but no provenance map, so run Create Skill (CS) from a brief when you need this audit trail.

See the [Verifying a Skill](/docs/verifying-a-skill.md) page for the full three-step audit on real skills, the test reports that log *exactly* where coverage falls short, and the scoring formula behind the default 80% pass threshold.

---

## Who's this for?

### The curious developer

Your agent just hallucinated a method that doesn't exist, again. You want this to stop, and you don't want to read a long architecture reference before running your first command.
→ Start with [Getting Started](/docs/getting-started.md).

### The BMAD user

You already use the BMAD Method, with its BMM phases (analysis, planning, solutioning, implementation) or its TEA (Test Architect) and BMB (BMAD Builder) modules, and you want to know where SKF fits.
→ Read [BMAD Synergy](/docs/bmad-synergy.md) for the phase-by-phase integration playbook.

### The skeptic

"AI docs for AI" sounds like the problem pretending to be the solution. You want receipts before you install anything.
→ Start with [Verifying a Skill](/docs/verifying-a-skill.md): the three-step audit on real skills, including the gaps their own test reports log.

### The OSS maintainer

You want to ship verified skills alongside your library releases: ready for `npx skills publish`, drift-detectable, and version-pinned.
→ See [Examples → OSS Maintainer Publishing Official Skills](/docs/examples.md#scenario-h-oss-maintainer-publishing-official-skills).

### The team lead evaluating adoption

You're considering running SKF across a brownfield platform (an existing, already-running codebase). Before you adopt it, you need to know that an update writes a new version beside the previous one instead of overwriting it, that hand-written `[MANUAL]` sections survive regeneration, and how the health check reports workflow problems.
→ Start with [Architecture](/docs/architecture.md), then [Workflows → Update Skill](/docs/workflows.md#update-skill-us) and [Workflows → Terminal Step: Health Check](/docs/workflows.md#terminal-step-health-check).

---

## Not for you if…

- You want docs that hand-hold through every happy path with screenshots and emojis. SKF is a citation machine, not a tutorial series.
- You don't have Node.js ≥ 22, Python ≥ 3.11, and `uv` installed. SKF is a Node/Python toolchain at its core, and setup stops without `uv`.
- You have neither source code nor published documentation for the target. SKF compiles from one or both: a source repo (each citation names a file and line at a pinned commit) or doc URLs (citations as `[EXT:{url}]`). A vague description with no upstream artifact to cite isn't enough.

Everything else is downstream of one question: *are the instructions your AI reads provably true?* If yes, SKF isn't adding value. If you can't be sure, SKF is the tool.

---

## Next

- **[Install SKF](/docs/getting-started.md#install)**: Node ≥ 22, Python ≥ 3.11, `uv`, and one `npx` command
- **[Audit a skill in 60 seconds](/docs/verifying-a-skill.md)**: see the receipts before you install
- **[Browse real skills](https://github.com/armelhbobdad/oh-my-skills)**: four Deep-tier skills, all shipping their audit trails
