---
title: Why Skill Forge?
description: The strategic case for SKF — the problem it solves, how it compares to alternatives, who it's for, and who it isn't.
---

Skill Forge is the only AI-skills toolchain where every claim your agent reads cites a file, a line, and a commit SHA. Not "sourced from training data." Not "retrieved from context." **Cited.** You can open the upstream repo at the pinned commit and see the function exists — in under a minute. That's the wedge. This page explains why it matters, how SKF compares to alternatives, and who it's for.

---

## The problem you're hiring SKF to solve

Your AI agents read your codebase through the lens of whatever happened to be in their training data. When that training data is wrong, stale, or incomplete, your agent invents — function names that don't exist, parameter types that don't match, config options removed two versions ago. You catch some of it in review. You ship some of it by accident. Every sprint, your team spends hours untangling code that only compiles in the AI's imagination.

SKF treats this as a citation problem, not a model problem. If a skill claims `cognee.search()` takes `query_text` as its first parameter, SKF points to `cognee/api/v1/search/search.py:L26` at commit `3c048aa4` in the upstream repo. That's the whole pitch: **nothing is made up, and everything is falsifiable in 60 seconds.**

---

## How SKF compares

<div class="comparison-table">

| Approach | What it does well | Where it falls short |
|----------|-------------------|----------------------|
| Skill scaffolding (`npx skills init`) | Generates a spec-compliant skill file | The file is empty — you still have to write every instruction by hand |
| LLM summarization | Understands context and intent | Generates plausible-sounding content that may not match the actual API |
| RAG / context stuffing | Retrieves relevant code snippets | Returns fragments without synthesis — no coherent skill output |
| Manual authoring | High initial accuracy | Drifts as the source code changes, doesn't scale across dependencies |
| IDE built-in context (Copilot, Cursor) | Convenient, zero setup | Uses generic training data, not your project's specific integration patterns |
| **Skill Forge** | **Every instruction cites upstream `file:line` at a pinned commit. Falsifiable in 60 seconds.** | **Coverage depends on which tools you've installed (Quick / Forge / Forge+ / Deep tiers).** |

</div>

---

## What "falsifiable in 60 seconds" actually means

Pick any symbol in any SKF-compiled skill. Three clicks:

1. Open the skill's `metadata.json` — it names the upstream repo and the exact commit SHA.
2. Open the skill's `provenance-map.json` — find your symbol; it lists the file and line.
3. Visit the upstream repo at that commit and that line. The signature in the skill should match.

If it doesn't, **that's a bug.** [Open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) and SKF republishes the skill with a new commit SHA and a new provenance map. No other AI-skills tool treats disagreement between claim and source as a defect. SKF does.

See the [Verifying a Skill](../verifying-a-skill/) page for the full three-step audit on real skills, the test reports that log *exactly* where coverage falls short, and the scoring formula behind the 80% pass threshold.

---

## Who's this for?

### The curious developer

Your agent just hallucinated a method that doesn't exist, again. You want this to stop, and you don't want to read a 569-line architecture page before running your first command.
→ Start with [Getting Started](../getting-started/).

### The BMAD user

You already use BMAD Method, BMM phases, TEA, or BMB, and you want to know where SKF fits.
→ Read [BMAD Synergy](../bmad-synergy/) for the phase-by-phase integration playbook.

### The skeptic

"AI docs for AI" sounds like the problem pretending to be the solution. You want receipts before you install anything.
→ Start with [Verifying a Skill](../verifying-a-skill/) — the three-step audit on real skills, including the 1% that fails.

### The OSS maintainer

You want to ship verified skills alongside your library releases — `npx skills publish`-ready, drift-detectable, version-pinned.
→ See [Examples → OSS Maintainer Publishing Official Skills](../examples/#scenario-h-oss-maintainer-publishing-official-skills).

### The team lead evaluating adoption

You're considering running SKF across a brownfield platform. You need to know about rollback safety, `[MANUAL]` section preservation, and the health-check feedback loop before committing.
→ Start with [Architecture](../architecture/), then [Workflows → Workflow Health Check](../workflows/#terminal-step-health-check).

---

## Not for you if…

- You want docs that hand-hold through every happy path with screenshots and emojis. SKF is a citation machine, not a tutorial series.
- You don't have Node.js ≥ 22 and Python ≥ 3.10 installed. SKF is a Node/Python toolchain at its core.
- You have neither source code nor published documentation for the target. SKF compiles from one or both — a source repo (citations as `file:line@SHA`) or doc URLs (citations as `[EXT:{url}]`). A vague description with no upstream artifact to cite isn't enough.

Everything else is downstream of one question: *are the instructions your AI reads provably true?* If yes, SKF isn't adding value. If you can't be sure, SKF is the tool.

---

## Next

- **[Install SKF](../getting-started/#install)** — Node ≥ 22, Python ≥ 3.10, `uv`, one `npx` command
- **[Audit a skill in 60 seconds](../verifying-a-skill/)** — see the receipts before you install
- **[Browse real skills](https://github.com/armelhbobdad/oh-my-skills)** — four Deep-tier skills, all shipping their audit trails
