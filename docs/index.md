---
title: Skill Forge (SKF)
description: Every instruction your AI reads cites a file, a line, and a commit SHA. Verify any claim in 60 seconds.
template: splash
hero:
  title: Skill Forge
  tagline: Every instruction your AI reads cites a file, a line, and a commit SHA.
  actions:
    - text: Why Skill Forge?
      link: ./why-skf/
      icon: right-arrow
      variant: primary
    - text: Install
      link: ./getting-started/#install
      icon: right-arrow
      variant: secondary
---

## The problem

AI agents hallucinate API calls. They invent function names, guess parameter types, and produce code that doesn't compile.

## The fix

Skill Forge reads the source and hands your agent the truth — with receipts. Every function signature, every parameter type, every usage pattern traces back to a file, a line, and a commit SHA in the upstream repository.

<div class="receipt-sample">
  <span class="receipt-sample__label">A receipt looks like</span>
  <code class="receipt-sample__chip">[AST:cognee/api/v1/search/search.py:L26]</code>
  <span class="receipt-sample__check" aria-label="verified">✓</span>
</div>

If SKF can't cite a source, it doesn't include the instruction.

<p class="cta-pill"><a href="./verifying-a-skill/">Verify any claim in 60 seconds →</a></p>

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

## Quick install

Requires [Node.js](https://nodejs.org/) >= 22, [Python](https://www.python.org/) >= 3.10, and [uv](https://docs.astral.sh/uv/).

```bash
npx bmad-module-skill-forge install
```

Then generate your first skill:

```
@Ferris SF                       # Set up your forge
@Ferris deepwiki <repo-or-url>   # Zero-ceremony: a repo or doc URL → verified skill
@Ferris QS <package>             # Or a fast skill from a package name in under a minute
```

[deepwiki](./deepwiki/) is the recommended starting point — one command, no configuration. See [Getting Started](./getting-started/) for platform support, tier selection, and troubleshooting.
