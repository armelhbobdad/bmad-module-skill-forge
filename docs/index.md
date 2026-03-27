---
title: Skill Forge (SKF)
description: Turn code and docs into instructions AI agents can actually follow
template: splash
hero:
  title: Skill Forge (SKF)
  tagline: Turn code and docs into instructions AI agents can actually follow.
  actions:
    - text: Getting Started
      link: ./getting-started/
      icon: right-arrow
      variant: primary
    - text: View on GitHub
      link: https://github.com/armelhbobdad/bmad-module-skill-forge
      icon: external
---

## What does Skill Forge do?

AI agents hallucinate API calls. They invent function names, guess parameter types, and produce code that doesn't compile. Skill Forge fixes this by analyzing code repositories, documentation, and developer discourse — extracting real signatures and patterns and compiling them into verified instruction files that any AI agent can follow. Every instruction traces back to where it came from. Generated skills can also include executable scripts and static assets extracted from the source repository, each with full provenance tracking.

## Quick Install

Requires [Node.js](https://nodejs.org/) >= 22.

```bash
npx bmad-module-skill-forge install
```

Then set up your environment and generate your first skill:

```
@Ferris SF              # Set up your forge
@Ferris QS <package>    # Generate a skill in under a minute
```

See the [Getting Started](./getting-started/) guide for full installation and usage instructions.

## Documentation

- **[Getting Started](./getting-started/)** — Installation, prerequisites, and your first skill
- **[Concepts](./concepts/)** — Plain-English definitions of key terms (provenance, tiers, drift, and more)
- **[How It Works](./how-it-works/)** — Architecture, capability model, output format, and design decisions
- **[Workflows](./workflows/)** — All 12 workflows with commands and connection diagrams
- **[Agents](./agents/)** — Ferris: the AI agent that runs all SKF workflows
- **[Examples](./examples/)** — Real-world scenarios, tips, and troubleshooting

## Support

- **Issues**: [GitHub Issues](https://github.com/armelhbobdad/bmad-module-skill-forge/issues)
