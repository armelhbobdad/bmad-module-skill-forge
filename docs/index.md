---
title: Skill Forge (SKF)
description: "Every instruction your AI reads cites its source: a file and line at a pinned commit, or a documentation URL. Verify any claim in 60 seconds."
template: splash
hero:
  title: Skill Forge
  tagline: "Every instruction your AI reads cites its source: a file and line at a pinned commit, or a documentation URL."
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

Skill Forge reads a library's source code and docs and writes a skill: an instruction file (SKILL.md) your AI agent loads before it writes code. Every function signature, parameter type, and usage pattern in it comes with a receipt. The receipt points back to where it came from: a file and line at a pinned commit in the upstream repository, or the documentation page it was read from.

<div class="receipt-sample">
  <span class="receipt-sample__label">An ast-grep receipt looks like</span>
  <code class="receipt-sample__chip">[AST:cognee/api/v1/search/search.py:L27]</code>
  <span class="receipt-sample__check" aria-label="verified">✓</span>
</div>

When SKF reads a definition by eye instead, the receipt says so: `[SRC:...]`, with a lower confidence label. When SKF can't cite a source, it leaves the instruction out. The main exception is Quick Skill (QS), a fast, best-effort draft with no receipt on each instruction.

<!-- Raw HTML bypasses rehype-markdown-links, so this href ships verbatim and
     cannot take the `/docs/*.md` form the Markdown links use: nothing would
     rewrite it into a route and the site would 404. It stays site-relative,
     which is correct here because this page is the site root. That makes it
     the one link in docs/ that does not also resolve on GitHub. -->

<p class="cta-pill"><a href="./verifying-a-skill/">Verify any claim in 60 seconds →</a></p>

## How SKF compares

<div class="comparison-table">

| Approach | What it does well | Where it falls short |
|----------|-------------------|----------------------|
| Skill scaffolding (`npx skills init`) | Creates a SKILL.md template in the standard skill format | The template holds only placeholder text, so you still write every instruction by hand |
| LLM summarization | Understands context and intent | Generates plausible-sounding content that may not match the actual API |
| RAG (retrieval) or pasting code into the prompt | Finds relevant code snippets | Hands over loose fragments, not a finished skill your agent can follow |
| Manual authoring | High initial accuracy | Drifts as the source code changes, doesn't scale across dependencies |
| IDE built-in context (Copilot, Cursor) | Convenient, zero setup | Uses generic training data, not your project's specific integration patterns |
| **Skill Forge** | **Every instruction cites its source: an upstream `file:line` at a pinned commit, or a doc URL for docs-only skills. You can check any claim in 60 seconds.** | **How deep it digs depends on which analysis tools you have installed. SKF detects them and picks a tier for you: Quick, Forge, Forge+ or Deep.** |

</div>

## Quick install

Requires [Node.js](https://nodejs.org/) >= 22, [Python](https://www.python.org/) >= 3.11, and [uv](https://docs.astral.sh/uv/), the tool SKF uses to run its Python scripts.

```bash
npx bmad-module-skill-forge install
```

Then open your AI coding tool (Claude Code, Cursor, GitHub Copilot and others) and start Ferris, the Skill Forge agent the installer set up there: type `/skf-forger` (`$skf-forger` in Codex), or ask your tool to talk to Ferris. Each line below is a request to Ferris, written as `@Ferris <code>`. Generate your first skill:

```
@Ferris SF                         # Set up your forge (once per project)
@Ferris forge-auto <repo-or-url>   # One command: a repo or doc URL in, a tested skill out
@Ferris QS <package>               # Or a quick best-effort draft from a package name
```

[forge-auto](/docs/forge-auto.md) is the recommended starting point. Once SF has run, it takes one command and asks you nothing along the way. It scopes, compiles, tests, and exports the skill, then adds it to your agent's context file (such as CLAUDE.md or AGENTS.md). See [Getting Started](/docs/getting-started.md) for platform support, the tools that decide your tier, and troubleshooting.
