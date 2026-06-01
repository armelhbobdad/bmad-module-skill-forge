---
title: How It Works
description: A plain-English walkthrough of Skill Forge compiling one skill from a real library, end to end.
---

Skill Forge reads your code, extracts what your AI agents actually need, and compiles it into instructions with citations. This page walks through what that looks like end-to-end. For the machinery behind it, see [Architecture](../architecture/). For what ships inside a skill, see [Skill Model](../skill-model/).

---

## A walkthrough: building a cognee skill

Your AI agent keeps hallucinating cognee API calls. You run one command:

```
@Ferris QS https://github.com/topoteretes/cognee
```

In under a minute, you get a `SKILL.md` your agent can load — with every instruction traceable to a specific file and line in cognee's source code. Here's what happens between those two moments.

### 1. Ferris picks a workflow

`QS` is a trigger — short for *Quick Skill*. Ferris is the single AI agent that runs every Skill Forge workflow. He reads the trigger, loads the Quick Skill workflow, and prepares the context he needs to do the job.

### 2. The workflow resolves your target

Ferris confirms the repository exists, detects its language, finds its version from the source manifest (`pyproject.toml`, `package.json`, etc.), and records the exact commit SHA he'll read from. This is the anchor — everything that follows traces back to this one commit.

### 3. He extracts the API

He reads cognee's source code, identifies the public exports, and pulls out function signatures, parameter types, and return types. At the Forge tier (with ast-grep installed), each signature is verified against the real syntax tree of the source. At Quick tier (no extra tools), he reads the file directly. Either way, nothing is invented — if he can't cite it, he doesn't include it.

### 4. He writes the skill with receipts

Each instruction in the output carries a receipt:

```python
await cognee.search(  # [AST:cognee/api/v1/search/search.py:L26]
    query_text="What does Cognee do?"
)
```

That tag means: *this came from AST extraction of this exact file at this exact line.* You can click through to the upstream source at the pinned commit and see it yourself.

### 5. You get a skill package

Ferris writes a `SKILL.md` (the full instruction manual your agent loads on demand) and a `context-snippet.md` (an 80–120 token index). The snippet gets injected into your platform context file (`CLAUDE.md`, `AGENTS.md`, or `.cursorrules`) as an always-on reminder: *"This skill exists; read it before writing cognee code."* Both halves are load-bearing — see the [Dual-Output Strategy](../skill-model/#dual-output-strategy) for why.

### 6. The audit trail stays on disk

Alongside the skill, Ferris leaves a `provenance-map.json` (every receipt), an `evidence-report.md` (build audit trail), and the compilation config (`skill-brief.yaml`). Commit these with the skill and any teammate — or any skeptic — can reproduce the same output from the same source.

That's the whole pipeline. One trigger in, one verifiable skill out, every claim traceable back to a file and a commit.

---

## Next

- **[Architecture](../architecture/)** — how Ferris loads workflows, how sub-agents handle large extractions, how the 7 tools resolve conflicts, where artifacts land on disk
- **[Skill Model](../skill-model/)** — what a skill contains, confidence tiers (T1 / T2 / T3), capability tiers (Quick / Forge / Forge+ / Deep), and the dual-output strategy
- **[Verifying a Skill](../verifying-a-skill/)** — the 60-second audit recipe and how completeness scoring works
- **[BMAD Synergy](../bmad-synergy/)** — how SKF fits alongside BMAD Method, TEA, BMB, and other modules
