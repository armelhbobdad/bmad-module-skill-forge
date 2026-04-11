<div align="center">

<img src="website/public/img/skf-logo.svg" alt="Skill Forge Logo" width="120" />

# Skill Forge (SKF)

**Turn code and docs into instructions AI agents can actually follow.**

[![Quality & Validation](https://github.com/armelhbobdad/bmad-module-skill-forge/actions/workflows/quality.yaml/badge.svg)](https://github.com/armelhbobdad/bmad-module-skill-forge/actions/workflows/quality.yaml)
[![npm](https://img.shields.io/npm/v/bmad-module-skill-forge)](https://www.npmjs.com/package/bmad-module-skill-forge)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![BMad Module](https://img.shields.io/badge/BMad-module-blue)](https://github.com/bmad-code-org/BMAD-METHOD)
[![Python Version](https://img.shields.io/badge/python-%3E%3D3.10-blue?logo=python&logoColor=white)](https://www.python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet?logo=uv)](https://docs.astral.sh/uv/)
[![Docs](https://img.shields.io/badge/docs-online-green)](https://armelhbobdad.github.io/bmad-module-skill-forge/)
[![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289da?logo=discord&logoColor=white)](https://discord.gg/gk8jAdXWmj)
[![GitHub stars](https://img.shields.io/github/stars/armelhbobdad/bmad-module-skill-forge?style=social)](https://github.com/armelhbobdad/bmad-module-skill-forge/stargazers)

*Skill Forge analyzes your code repositories, documentation, and developer discourse to build verified instruction files for AI agents. Every instruction links back to where it came from — nothing is made up.*

**If SKF helps your agent stop hallucinating, give it a ⭐ — it helps others find this tool.**

</div>

---

## The Problem

You ask an AI agent to use a library. It invents function names that don't exist. It guesses parameter types. You paste documentation into the context — it still gets details wrong. You write instructions by hand — they go stale the moment the code changes.

This isn't an edge case. It's the default experience.

## How Skill Forge Fixes This

1. **Analyzes your sources** — extracts real function signatures, types, and patterns from code repositories, documentation websites, and developer discourse
2. **Compiles verified instruction files** — every instruction links to the exact file and line it came from
3. **Version-aware** — skills are stored per-version, so updating to v2.0 doesn't break your v1.x skill. Compatible with [skill.sh](https://skill.sh) and [npx skills](https://www.npmjs.com/package/skills)
4. **Manageable lifecycle** — rename skills and drop deprecated versions without manual file surgery. Transactional safety for destructive operations.
5. **Follows an open standard** — skills comply with the [agentskills.io](https://agentskills.io) spec and work across Claude, Cursor, Copilot, and other AI agents

## Before vs After

**Without SKF** — your agent guesses:

```python
import cognee

# Agent hallucinates: sync call, wrong parameter name, missing await
results = cognee.search("What does Cognee do?", mode="graph")
```

**With SKF** — your agent reads the verified skill:

```python
import cognee

# Agent follows the skill instruction:
# `search(query_text: str, query_type: SearchType = GRAPH_COMPLETION) -> List[SearchResult]`
# [AST:cognee/api/v1/search/search.py:L26]
results = await cognee.search(
    query_text="What does Cognee do?",
    query_type=cognee.SearchType.GRAPH_COMPLETION
)
```

The skill told the agent the real function name, the real parameters, and that the call requires `await` — all traced to the exact source line. This is from a [real generated skill](https://github.com/armelhbobdad/oh-my-skills).

## Install

Requires [Node.js](https://nodejs.org/) >= 22, [Python](https://www.python.org/) >= 3.10, and [uv](https://docs.astral.sh/uv/) (Python package runner).

```bash
npx bmad-module-skill-forge install
```

You'll be prompted for project name, output folders, and IDE configuration. See the [docs](https://armelhbobdad.github.io/bmad-module-skill-forge/getting-started/) for other install methods.

## Quick Start

1. **Set up your environment:** `@Ferris SF` — detects your tools and sets your capability tier
2. **Generate your first skill:** `@Ferris QS <package-name>` — creates a verified skill in under a minute
3. **Full quality path:** `@Ferris BS` → clear session → `@Ferris CS` — brief first, then compile for maximum accuracy
4. **Pipeline mode:** `@Ferris forge cocoindex` — chains Brief → Create → Test → Export in one command

> **Tip:** Start a fresh conversation before each workflow (or use pipeline mode to chain them automatically). SKF workflows load significant context — clearing between them prevents interference.

See the [workflows docs](https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/) for all 14 available workflows, pipeline aliases, and headless mode.

## Help SKF Improve — Let Workflows Finish

Every SKF workflow ends with a **health check** — a reflection step where Ferris captures any friction, bugs, or gaps from the session and offers to file them as GitHub issues (with your approval). Clean runs exit in one line; when something breaks, this is how SKF learns to do better.

**Please let workflows run to completion.** If you cancel early or the terminal step gets skipped, the feedback is lost. If the health check didn't run, you can:

- Ask Ferris directly: `@Ferris please run the workflow health check for this session`, or
- [Open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) — every concrete report makes SKF sharper for the next person.

See the [Workflow Health Check](https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/#terminal-step-health-check) docs for details.

## Who Is This For?

- **You use AI agents to write code** and they keep getting API calls wrong — hallucinating function names, guessing parameter types, inventing methods that don't exist
- **You maintain a library** and want to ship official, verified instruction files so AI agents use your API correctly
- **You manage a codebase with many dependencies** and want a consolidated "stack skill" that teaches your agent how all the pieces fit together
- **You use a SaaS API or closed-source tool** with no public code — SKF can generate skills from documentation alone
- **You need different skills for different use cases** from the same target — compile multiple skills with different scopes from one repo or doc set (e.g., a core API skill and a migration guide skill)

## Learn More

- **[Getting Started](https://armelhbobdad.github.io/bmad-module-skill-forge/getting-started/)** — Installation, prerequisites, and your first skill
- **[Concepts](https://armelhbobdad.github.io/bmad-module-skill-forge/concepts/)** — Plain-English definitions of all key terms
- **[How It Works](https://armelhbobdad.github.io/bmad-module-skill-forge/how-it-works/)** — Architecture, capability tiers, output format, and design decisions
- **[Workflows](https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/)** — All 14 workflows with commands and connection diagrams
- **[Agents](https://armelhbobdad.github.io/bmad-module-skill-forge/agents/)** — Ferris: the AI agent that runs all SKF workflows
- **[Examples](https://armelhbobdad.github.io/bmad-module-skill-forge/examples/)** — Real-world scenarios, tips, and troubleshooting
- **[BMAD Synergy](https://armelhbobdad.github.io/bmad-module-skill-forge/bmad-synergy/)** — How SKF workflows pair with BMAD CORE phases and optional modules

## Acknowledgements

SKF builds on these excellent open-source tools:

| Tool                                                         | Role in SKF                                                        |
|--------------------------------------------------------------|--------------------------------------------------------------------|
| [agentskills.io](https://github.com/agentskills/agentskills) | Skill specification and ecosystem standard                         |
| [GitHub CLI](https://cli.github.com/)                        | Source code access and repository intelligence (all tiers)         |
| [ast-grep](https://github.com/ast-grep/ast-grep)             | AST-based structural code extraction (Forge/Forge+/Deep tiers)     |
| [ast-grep MCP](https://github.com/ast-grep/ast-grep-mcp)     | MCP server for memory-efficient AST queries (recommended)          |
| [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) | Semantic code search and file discovery pre-ranking (Forge+ tier)  |
| [QMD](https://github.com/tobi/qmd)                           | Local hybrid search engine for knowledge indexing (Deep tier)      |
| [skill-check](https://github.com/thedaviddias/skill-check)   | Skill validation, auto-fix, quality scoring, and security scanning |
| [Snyk Agent Scan](https://github.com/snyk/agent-scan)   | Security scanning for prompt injection and data exposure (optional) |
| [tessl](https://tessl.io)                                     | Content quality review, actionability scoring, and AI judge evaluation |
| [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD)  | Agent-workflow framework that SKF extends as a module              |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**Skill Forge (SKF)** — A standalone [BMad](https://github.com/bmad-code-org/BMAD-METHOD) module for agent skill compilation.

[![Contributors](https://contrib.rocks/image?repo=armelhbobdad/bmad-module-skill-forge)](https://github.com/armelhbobdad/bmad-module-skill-forge/graphs/contributors)

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for contributor information.
