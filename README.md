<div align="center">

<img src="website/public/img/skf-logo.svg" alt="Skill Forge Logo" width="120" />

# Skill Forge (SKF)

**Turn code and docs into instructions AI agents can actually follow.**

[![Quality & Validation](https://github.com/armelhbobdad/bmad-module-skill-forge/actions/workflows/quality.yaml/badge.svg)](https://github.com/armelhbobdad/bmad-module-skill-forge/actions/workflows/quality.yaml)
[![npm](https://img.shields.io/npm/v/bmad-module-skill-forge)](https://www.npmjs.com/package/bmad-module-skill-forge)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![BMAD Module](https://img.shields.io/badge/BMAD-module-blue)](https://github.com/bmad-code-org/BMAD-METHOD)
[![Python Version](https://img.shields.io/badge/python-%3E%3D3.10-blue?logo=python&logoColor=white)](https://www.python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet?logo=uv)](https://docs.astral.sh/uv/)
[![Docs](https://img.shields.io/badge/docs-online-green)](https://armelhbobdad.github.io/bmad-module-skill-forge/)
[![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289da?logo=discord&logoColor=white)](https://discord.gg/gk8jAdXWmj)
[![GitHub stars](https://img.shields.io/github/stars/armelhbobdad/bmad-module-skill-forge?style=social)](https://github.com/armelhbobdad/bmad-module-skill-forge/stargazers)

_Skill Forge analyzes your code repositories, documentation, and developer discourse to build verified instruction files for AI agents. Every instruction links back to a specific file and line in the source it was compiled from._

**If SKF fixes your agent's API guesses, give it a ⭐ — it helps others find this tool.**
**If it saved you an afternoon, [grab me a coffee ☕](https://buymeacoffee.com/armelhbobdad) — it helps me keep forging.**

</div>

---

## The Problem

You ask an AI agent to use a library. It invents function names that don't exist. It guesses parameter types. You paste documentation into the context — it still gets details wrong. You write instructions by hand — they go stale the moment the code changes.

This isn't an edge case. It's the default experience.

For the full story behind SKF, read [_Hallucination has a line number_](https://medium.com/@armelhbobdad/hallucination-has-a-line-number-32209b4688de) on Medium.

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
# [AST:cognee/api/v1/search/search.py:L27]
results = await cognee.search(
    query_text="What does Cognee do?",
    query_type=cognee.SearchType.GRAPH_COMPLETION
)
```

The skill told the agent the real function name, the real parameters, and that the call is async — all traced to the exact source line. This example is from the real [`oms-cognee`](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/oms-cognee/1.0.0/oms-cognee/SKILL.md) skill in [**oh-my-skills**](https://github.com/armelhbobdad/oh-my-skills) — SKF's reference output. The [**Verifying a Skill**](#verifying-a-skill) section below shows how to walk the citation chain yourself.

## Install

Linux, Windows, and macOS supported ([platform details](https://armelhbobdad.github.io/bmad-module-skill-forge/getting-started/#platform-support)). Requires [Node.js](https://nodejs.org/) >= 22, [Python](https://www.python.org/) >= 3.10, and [uv](https://docs.astral.sh/uv/) (Python package runner).

```bash
npx bmad-module-skill-forge install
```

You'll be prompted for project name, output folders, and IDE configuration. When the install completes, open your IDE and invoke `@Ferris SF` to confirm Ferris is reachable. Ferris reports your detected tools and capability tier. See the [docs](https://armelhbobdad.github.io/bmad-module-skill-forge/getting-started/) for other install methods.

## Quick Start

1. **Set up your environment:** `@Ferris SF` _(Setup Forge)_ — detects your tools and sets your capability tier
2. **Generate your first skill:** `@Ferris QS <package-name>` _(Quick Skill)_ — creates a verified skill in under a minute
3. **Full quality path:** `@Ferris forge <your-library>` chains Brief → Create → Test → Export automatically — or run manually: `@Ferris BS` → clear session → `@Ferris CS` for maximum control

> **Tip:** Start a fresh conversation before each workflow, or use pipeline mode to chain them automatically. SKF workflows load significant context; clearing between them prevents interference.

See the [workflows docs](https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/) for all available workflows, pipeline aliases, and headless mode.

## Who Is This For?

- **You use AI agents to write code** and they keep guessing API calls wrong
- **You maintain a library** and want to ship official, verified instruction files so AI agents use your API correctly
- **You manage a codebase with many dependencies** and want a consolidated "stack skill" that teaches your agent how all the pieces fit together
- **You use a SaaS API or closed-source tool** with no public code — SKF can generate skills from documentation alone
- **You need different skills for different use cases** from the same target — compile multiple skills with different scopes from one repo or doc set (e.g., a core API skill and a migration guide skill)

## How SKF Compares

A skeptical reader is probably already considering one of these alternatives:

|                            | **Skill Forge**                           | MCP doc servers   | Hand-edited `.cursorrules` | awesome-\* lists |
| -------------------------- | ----------------------------------------- | ----------------- | -------------------------- | ---------------- |
| Reproducible from source   | AST extraction + pinned commit            | varies; opaque    | whatever you wrote         | none             |
| Version-pinned & immutable | yes — per-version directories             | runtime-dependent | rots silently              | no               |
| Audit trail                | `provenance-map.json` + test + evidence   | depends on server | none                       | none             |
| Runtime cost               | zero (markdown + JSON)                    | a running process | zero                       | zero             |
| Lifecycle tooling          | rename, drop, update, export transactions | varies            | file surgery               | none             |
| Falsifiable                | yes — three steps, 60 seconds             | rarely            | no                         | no               |

The others aren't bad. They solve different problems. **SKF solves exactly one: the claim your agent is reading about a library was true at a specific commit on a specific day, and you can prove it in under a minute.**

## How Skill Forge Fixes This

SKF extracts real function signatures, types, and patterns from code, docs, and developer discourse — every instruction links to the exact file and line it came from. On top of that foundation:

1. **Version-pinned** — skills are stored per-version, so updating to v2.0 doesn't replace your v1.x skill. Compatible with [skills.sh](https://skills.sh) and [npx skills](https://www.npmjs.com/package/skills)
2. **Lifecycle tooling** — rename skills and drop deprecated versions without manual file surgery. Destructive operations are transactional.
3. **Follows an open standard** — skills comply with the [agentskills.io](https://agentskills.io) spec and work across Claude, Cursor, Copilot, and other AI agents

> **Every skill ships two files — `SKILL.md` (the full instruction set, loaded on trigger) and `context-snippet.md` (an 80–120 token always-on index injected into `CLAUDE.md` / `AGENTS.md` / `.cursorrules`). Why both?** Per Vercel's agent evals, passive context achieves a **100% pass rate vs. 79% for active skills loaded alone** (see [Skill Model → Dual-Output Strategy](https://armelhbobdad.github.io/bmad-module-skill-forge/skill-model/#dual-output-strategy)).

## Verifying a Skill

You can falsify any AST citation in an SKF-compiled skill in under a minute:

1. **Open the skill's `provenance-map.json`** — find your symbol; read its `source_file` and `source_line`.
2. **Open the skill's `metadata.json`** — read `source_commit` and `source_repo`.
3. **Jump to the upstream repo at that commit**, open that file, find that line. The signature in `SKILL.md` should match the one you're reading.

If it doesn't, that's a bug — open an issue and SKF will republish with a new commit SHA and a new provenance map. Falsifiability isn't a feature; it's the whole deal.

**Reference output: [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills)** — four Deep-tier skills compiled by SKF (cocoindex, cognee, Storybook v10, uitripled), each shipping its full audit trail in-repo. Scores range from 99.0% to 99.49%. Every claim walks to an upstream line in under 60 seconds. Serves as both the worked example for this section and ongoing proof that the pipeline does what it says.

## Help SKF Improve

Workflows end with a health check that can file bug or friction reports as GitHub issues (auto-deduped by fingerprint — re-reporting is safe). **Please let workflows run to completion**, or [open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) directly. [Full details →](https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/#terminal-step-health-check)

## Learn More

The docs are organized into three buckets — **Why** (start here), **Try** (do stuff), and **Reference** (look things up):

**Why**

- **[Why Skill Forge?](https://armelhbobdad.github.io/bmad-module-skill-forge/why-skf/)** — The JTBD pitch, persona router, and the honest anti-pitch
- **[Verifying a Skill](https://armelhbobdad.github.io/bmad-module-skill-forge/verifying-a-skill/)** — The 60-second audit recipe and scoring formula

**Try**

- **[Getting Started](https://armelhbobdad.github.io/bmad-module-skill-forge/getting-started/)** — Install, first skill, prereqs, and config
- **[How It Works](https://armelhbobdad.github.io/bmad-module-skill-forge/how-it-works/)** — Plain-English walkthrough of one skill being built, end to end
- **[Examples](https://armelhbobdad.github.io/bmad-module-skill-forge/examples/)** — Real-world scenarios with full command transcripts
- **[Workflows](https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/)** — All 14 workflows with commands and connection diagrams

**Reference**

- **[Concepts](https://armelhbobdad.github.io/bmad-module-skill-forge/concepts/)** — Seven load-bearing terms: provenance, confidence tiers, drift, and more
- **[Architecture](https://armelhbobdad.github.io/bmad-module-skill-forge/architecture/)** — Runtime flow, 7 tools, workspace artifacts, security, and the design decisions behind them
- **[Skill Model](https://armelhbobdad.github.io/bmad-module-skill-forge/skill-model/)** — Capability tiers, confidence tiers, output format, dual-output strategy, ownership model
- **[Agents](https://armelhbobdad.github.io/bmad-module-skill-forge/agents/)** — Ferris: the single AI agent that runs every SKF workflow
- **[BMAD Synergy](https://armelhbobdad.github.io/bmad-module-skill-forge/bmad-synergy/)** — How SKF pairs with BMAD CORE phases and optional modules (TEA, BMB, GDS, CIS)
- **[Troubleshooting](https://armelhbobdad.github.io/bmad-module-skill-forge/troubleshooting/)** — Common errors (forge setup, ecosystem checks, tier confidence) and how to resolve them

## Acknowledgements

SKF builds on these excellent open-source tools:

| Tool                                                             | Role in SKF                                                            |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| [agentskills.io](https://github.com/agentskills/agentskills)     | Skill specification and ecosystem standard                             |
| [GitHub CLI](https://cli.github.com/)                            | Source code access and repository intelligence (all tiers)             |
| [ast-grep](https://github.com/ast-grep/ast-grep)                 | AST-based structural code extraction (Forge/Forge+/Deep tiers)         |
| [ast-grep MCP](https://github.com/ast-grep/ast-grep-mcp)         | MCP server for memory-efficient AST queries (recommended)              |
| [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) | Semantic code search and file discovery pre-ranking (Forge+ tier)      |
| [QMD](https://github.com/tobi/qmd)                               | Local hybrid search engine for knowledge indexing (Deep tier)          |
| [skill-check](https://github.com/thedaviddias/skill-check)       | Skill validation, auto-fix, quality scoring, and security scanning     |
| [Snyk Agent Scan](https://github.com/snyk/agent-scan)            | Security scanning for prompt injection and data exposure (optional)    |
| [tessl](https://tessl.io)                                        | Content quality review, actionability scoring, and AI judge evaluation |
| [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)      | Agent-workflow framework that SKF extends as a module                  |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

Past releases are documented in [CHANGELOG.md](CHANGELOG.md).

## Versioning & Stability

The v1.0.0 public API contract is documented in [docs/STABILITY.md](docs/STABILITY.md).

## Release Process

Maintainers: see [docs/RELEASING.md](docs/RELEASING.md) for branch-protection rules, required status checks, the [`release` environment with required-reviewer gate](docs/RELEASING.md#release-environment), the [npm Trusted Publisher registration](docs/RELEASING.md#npm-trusted-publisher) (OIDC-backed publish, auto-provenance), and the [rollback playbook](docs/RELEASING.md#rollback-playbook) covering seven failure scenarios.

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**Skill Forge (SKF)** — A standalone [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module for agent skill compilation.

[![Contributors](https://contrib.rocks/image?repo=armelhbobdad/bmad-module-skill-forge)](https://github.com/armelhbobdad/bmad-module-skill-forge/graphs/contributors)

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for contributor information.
