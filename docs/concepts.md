---
title: Concepts
description: Seven load-bearing terms for using and understanding Skill Forge — agent skills, provenance, confidence tiers, capability tiers, drift, version pinning, and the BMAD module.
---

These are the seven terms you'll meet in every other page of this site. Each one names something SKF does differently from generic docs tooling. For the full mechanism behind them, see [Architecture](/docs/architecture.md) and [Skill Model](/docs/skill-model.md).

---

## Agent Skills

An agent skill is an instruction file that tells an AI agent how to use your code. Instead of guessing your API from its training data, the agent reads the skill and gets the actual function names, parameter types, and usage patterns.

Skills follow the [agentskills.io](https://agentskills.io) open standard, so they work across Claude, Cursor, Copilot, and other AI tools.

**Example:** A skill for [cognee](https://github.com/topoteretes/cognee) tells your agent: "The function is `cognee.search()`, its first parameters are `query_text`, `query_type`, `user`, `datasets`, and `dataset_ids`, and it's defined at `cognee/api/v1/search/search.py:L26` (v1.0.0, commit `3c048aa4`)." Every parameter and location is AST-verified from the actual source code.

---

## Provenance

Provenance means every instruction in a skill traces back to where it came from. For code, that's a file and line number. For documentation, it's a URL. For developer discourse, it's an issue or PR reference. **If SKF can't point to a source, it doesn't include the instruction.**

**Examples** (from a [real generated skill](https://github.com/armelhbobdad/oh-my-skills)):
- `[AST:cognee/api/v1/search/search.py:L26]` — extracted from source code via AST parsing (T1)
- `[SRC:cognee/api/v1/session/__init__.py:L7]` — read from source code without AST verification (T1-low)
- `[QMD:cognee-temporal:issues.md]` — surfaced from indexed developer discourse (T2)
- `[EXT:docs.cognee.ai/getting-started/quickstart]` — sourced from external documentation (T3)

This is the opposite of how most AI tools work. They generate plausible-sounding content from training data; SKF only includes what it can cite. Quick-tier skills rely on best-effort source reading rather than AST verification — but even Quick skills cite their sources, and nothing ships without a citation.

---

## Confidence Tiers (T1/T1-low/T2/T3)

Each piece of information in a skill carries a confidence level based on where it came from:

- **T1 — AST extraction:** Pulled directly from source code via AST parsing. The function signature exists in the code at the pinned commit. Cited as `[AST:file:Lnn]`.
- **T1-low — Source reading:** Found by reading source files directly without AST parsing. The location is correct but the type signature may be inferred. Produced by Quick tier and by Forge/Forge+/Deep when ast-grep cannot parse a specific file. Cited as `[SRC:file:Lnn]`.
- **T2 — Evidence (Deep tier only):** Surfaced by QMD knowledge search from issues, PRs, changelogs, or documentation within the repository. Available only when QMD is installed (Deep tier). Reliable context, but less definitive than source code itself. Cited as `[QMD:collection:document]`. T2 has two temporal subtypes:
  - **T2-past** — Historical context (closed issues, merged PRs, changelogs) explaining API design decisions. Surfaces in the skill's `references/` directory.
  - **T2-future** — Forward-looking context (open PRs, deprecation warnings, RFCs) about upcoming changes. Surfaces in SKILL.md Section 4b (Migration & Deprecation Warnings) and `references/`.
- **T3 — External:** Pulled from external documentation or websites. Treated with caution and clearly marked. Cited as `[EXT:url]`.

Forge+ semantic discovery (via cocoindex-code) does not introduce a new confidence tier — it influences *which* files are extracted, not *how* they're cited. Discovered files are verified by ast-grep (T1) or source reading (T1-low).

---

## Capability Tiers (Quick/Forge/Forge+/Deep)

Your capability tier depends on which tools you have installed. Each tier builds on the previous one:

- **Quick** — No tools required. SKF reads source files and builds best-effort skills. Works in under a minute. GitHub CLI used when available.
- **Forge** — Adds [ast-grep](https://ast-grep.github.io). SKF uses AST parsing to verify instructions against the actual code structure.
- **Forge+** — Adds [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code). SKF uses semantic code search to discover relevant source regions before AST extraction, improving coverage on large codebases.
- **Deep** — Full pipeline: requires [ast-grep](https://ast-grep.github.io) + [GitHub CLI](https://cli.github.com) + [QMD](https://github.com/tobi/qmd) (all three). SKF indexes knowledge for semantic search and performs GitHub repository exploration. Skills get enriched with historical context, deprecation warnings, and cross-reference intelligence. CCC (cocoindex-code) enhances Deep tier when installed — ast-grep + gh + qmd + ccc gives maximum capability.

You don't need all tools to start. SKF detects what you have and sets your tier automatically. See [Skill Model → Progressive Capability Model](/docs/skill-model.md#progressive-capability-model) for the full technical treatment.

---

## Drift

Drift happens when the source code changes but the skill instructions haven't been updated to match. A skill might still reference a function that was renamed, removed, or had its signature changed upstream.

SKF detects drift by comparing the skill's recorded provenance against the current code. The `audit-skill` workflow (`@Ferris AS`) scans for these mismatches — for both individual skills and stack skills. Stack skills track per-library provenance and, in compose-mode, constituent freshness via metadata hash comparison.

**Example:** Your skill says `createUser(name: string)` but the function was renamed to `registerUser(name: string, email: string)` in the last release. That's drift. For stack skills, constituent drift occurs when an individual skill is updated but the stack hasn't been re-composed to reflect the changes.

---

## Version Pinning

Every skill records the exact version (or commit) of the source code it was built from. This means you always know which version of the library the instructions apply to.

By default, the version is auto-detected from the source (package.json, pyproject.toml, etc.). You can also target a specific version — either by specifying it during `@Ferris BS` (brief-skill) or by appending `@version` to a quick skill command (`@Ferris QS cognee@1.0.0`). This is especially useful for docs-only skills where no source code is available for auto-detection. When targeting a specific version on a remote repository, SKF resolves the matching git tag and clones from it — so the extracted API signatures actually reflect the target version's code, not just the label applied to whatever happens to be on the default branch.

When the source updates, you can re-run `@Ferris US` (update-skill) to regenerate the skill for the new version while preserving any manual additions you've made.

---

## BMAD Module

SKF is a plugin (called a "module") for [BMAD Method](https://docs.bmad-method.org/), a framework for running structured AI workflows. You don't need to know BMAD to use SKF — the standalone installer sets everything up.

If you already use BMAD, see [BMAD Synergy](/docs/bmad-synergy.md) for how SKF workflows pair with BMM phases and optional modules like TEA, BMB, and GDS.
