---
title: Troubleshooting
description: Common errors in Skill Forge — forge setup, ecosystem checks, tier confidence — and how to resolve them.
---

If something isn't working, start here. For general setup help see [Getting Started → Need help?](../getting-started/#need-help).

---

## Common errors

### "Setup cannot proceed: `uv` is not installed"

Surfaced by `/skf-setup` On Activation when `uv --version` is missing on `$PATH`. SKF helpers depend on `uv` to auto-resolve their Python dependencies via PEP 723 inline metadata; bare `python3` ignores that metadata and would fail later with `ModuleNotFoundError: No module named 'yaml'`. The probe halts the workflow up-front with one cohesive diagnostic instead of letting five steps each fail individually.

**Fix:** install `uv` from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`. `uv` is documented as a runtime prerequisite in [Getting Started → Prerequisites](../getting-started/#prerequisites-full-reference).

### "Setup cannot proceed: `_bmad/skf/config.yaml` was not found"

Surfaced by `/skf-setup` On Activation when the SKF install config is missing — typically because you invoked `/skf-setup` from a directory that is not an SKF-initialised project. The check runs before any file mutation so nothing is written.

**Fix:** from the project root, run `npx bmad-module-skill-forge install` (or `npx bmad-method install` and add SKF as a custom module — see [Getting Started → Install](../getting-started/#install)), then re-run `/skf-setup`. If you ARE in the right project but the file was deleted, restore it from version control or re-run the SKF installer. A separate "config.yaml is not valid YAML" diagnostic surfaces the parser error inline if the file exists but is malformed — open the file at the named path and repair the YAML.

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

### `@Ferris onboard` returns an error

The `onboard` alias was removed. Its replacement is [`deepwiki`](../deepwiki/), which does everything `onboard` did plus auto-scope, auto-brief, and a stricter 90% quality gate. Run `@Ferris deepwiki <repo-or-doc-url>` instead.

### deepwiki halted at the Test stage

deepwiki runs Test Skill with a stricter **90% quality threshold** (vs the default 80%), so a skill that scores below 90% halts at TS with a gap report rather than exporting a weak skill. Run `@Ferris US` to address the gaps it lists, then `@Ferris TS EX` to re-test and export. If 90% is stricter than you need, run the individual workflows or `forge` instead, which use the default threshold.

### My campaign stopped partway — how do I resume?

Campaign is designed for exactly this. State lives in `_campaign-state.yaml` on disk, so context death, a session timeout, or a machine restart loses nothing. Run `@Ferris campaign resume` — Ferris validates the state file, skips completed skills, and picks up from the next incomplete skill in dependency order. If the state file is corrupted, Ferris falls back to the `.bak` copy automatically. To re-process one specific skill, use `@Ferris campaign resume --from=<skill>`.

---

## Still stuck?

1. Run `@Ferris SF` to check your tool availability and current tier
2. Check `forge-tier.yaml` in your forger sidecar for your configuration
3. If `/bmad-help` is installed (via full BMAD Method), run it and describe your state — e.g. `/bmad-help my batch creation failed halfway, how do I resume?`
4. [File an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose) — SKF's [health check system](../workflows/#terminal-step-health-check) is the primary feedback channel, and manual issues feed the same pipeline
