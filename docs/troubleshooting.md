---
title: Troubleshooting
description: Common errors in Skill Forge — forge setup, ecosystem checks, tier confidence — and how to resolve them.
---

If something isn't working, start here. For general setup help see [Getting Started → Need help?](../getting-started/#need-help).

---

## Common errors

### Forge reports ast-grep is unavailable

If setup reports that ast-grep was not detected, install it to unlock the Forge tier: <https://ast-grep.github.io>. Re-run `@Ferris SF` afterward — your tier upgrades automatically.

### "No skill brief found"

Run `@Ferris BS` first to create a skill brief, or use `@Ferris QS` for brief-less generation. `CS` requires either a brief or a direct invocation with scope arguments.

### "Ecosystem check: official skill exists"

An official skill already exists for this package. Consider installing it with `npx skills add` instead of generating your own — the official skill is typically better tested and kept up-to-date by the library maintainer.

### Quick-tier skills have lower confidence scores

Quick tier reads source without AST analysis, so signatures are read directly from files rather than structurally verified. Install ast-grep to upgrade to the Forge tier for AST-verified signatures (T1 confidence) — see [Capability Tiers](../concepts/#capability-tiers-quickforgeforgedeep).

### Want semantic discovery for large codebases?

Install [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) to unlock the Forge+ tier. CCC indexes your codebase and pre-ranks files by semantic relevance before AST extraction, improving coverage on projects with 500+ files.

---

## Still stuck?

1. Run `@Ferris SF` to check your tool availability and current tier
2. Check `forge-tier.yaml` in your forger sidecar for your configuration
3. If `/bmad-help` is installed (via full BMAD Method), run it and describe your state — e.g. `/bmad-help my batch creation failed halfway, how do I resume?`
4. [File an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) — SKF's [health check system](../workflows/#terminal-step-health-check) is the primary feedback channel, and manual issues feed the same pipeline
