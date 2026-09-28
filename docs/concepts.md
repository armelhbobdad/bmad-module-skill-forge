---
title: Concepts
description: "Seven core terms for using and understanding Skill Forge: agent skills, provenance, confidence tiers, capability tiers, drift, version pinning, and the BMAD module."
---

These are the seven terms you'll meet in every other page of this site. Each one names something SKF does differently from generic docs tooling. For the full mechanism behind them, see [Architecture](/docs/architecture.md) and [Skill Model](/docs/skill-model.md).

Commands on this page look like `@Ferris AS`. Ferris is the SKF agent you talk to, and the two letters are the menu code of the workflow you want (`AS` is Audit Skill). See [Agents](/docs/agents.md) for the full menu.

---

## Agent Skills

An agent skill is an instruction file that tells an AI agent how to use your code. Instead of guessing your API from its training data, the agent reads the skill and gets the actual function names, parameter types, and usage patterns.

Skills follow the [agentskills.io](https://agentskills.io) open standard, so they work across Claude, Cursor, Copilot, and other AI tools.

**Example:** A skill for [cognee](https://github.com/topoteretes/cognee) tells your agent: "The function is `cognee.search()`, its first parameters are `query_text`, `query_type`, `user`, `datasets`, and `dataset_ids`, and it's defined at `cognee/api/v1/search/search.py:L27` (v1.0.0, commit `3c048aa4`)." Every parameter and location is AST-verified: SKF parsed the structure of the actual source code (its abstract syntax tree, or AST) to confirm it.

---

## Provenance

Provenance means every instruction in a skill traces back to where it came from. For code, that's a file and line number. For documentation, it's a URL. For developer discourse such as issues, pull requests, and changelogs, it's the indexed document the instruction came from. **If SKF can't point to a source, it doesn't include the instruction.**

**Examples** (from real generated skills in [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills)):
- `[AST:cognee/api/v1/search/search.py:L27]`: extracted from source code by AST parsing (T1)
- `[SRC:cognee/api/v1/add/add.py:L166]`: read from source code without AST verification (T1-low)
- `[QMD:oms-cognee-temporal:releases.md]`: found in indexed release notes and other developer discourse (T2)
- `[EXT:https://docs.cognee.ai/getting-started/quickstart]`: taken from external documentation (T3)

This is the opposite of how most AI tools work. They generate plausible-sounding content from training data; SKF only includes what it can cite. Skills compiled at the Quick tier rely on best-effort source reading rather than AST verification, but they still cite their sources, as `[SRC:file:Lnn]` (T1-low). Inside a compiled skill, the only content without a citation is clearly marked: sections you write yourself between `[MANUAL]` markers, and integrations labeled `[inferred from shared domain]` in a stack skill assembled from existing skills. Quick Skill (`@Ferris QS`) is the exception: it writes a fast, best-effort draft from the source and README, with no citation on each instruction and no provenance map.

---

## Confidence Tiers (T1/T1-low/T2/T3)

Each piece of information in a skill carries a confidence level based on where it came from:

- **T1 (AST extraction):** Pulled directly from source code via AST parsing. The function signature exists in the code at the pinned commit. Cited as `[AST:file:Lnn]`.
- **T1-low (source reading):** Found by reading source files directly without AST parsing. The location is correct but the type signature may be inferred. Produced by Quick tier, and by Forge, Forge+, or Deep when ast-grep cannot parse a specific file. Cited as `[SRC:file:Lnn]`.
- **T2 (evidence, Deep tier only):** Found by QMD, a local search engine that SKF uses to index the project's issues, pull requests, changelogs, and fetched documentation. Reliable context, but less definitive than source code itself. Cited as `[QMD:collection:document]`. T2 has two temporal subtypes:
  - **T2-past:** Historical context (closed issues, merged PRs, changelogs) explaining API design decisions. Surfaces in the skill's `references/` directory.
  - **T2-future:** Forward-looking context (open PRs, deprecation warnings, RFCs) about upcoming changes. Surfaces in the Migration & Deprecation Warnings section of SKILL.md, which appears only when there is such context, and in `references/`.
- **T3 (external):** Pulled from external documentation or websites. Treated with caution and clearly marked. Cited as `[EXT:url]`.

Forge+ semantic discovery (via cocoindex-code) does not introduce a new confidence tier. It changes *which* files are extracted, not *how* they're cited. Discovered files are verified by ast-grep (T1) or source reading (T1-low).

---

## Capability Tiers (Quick/Forge/Forge+/Deep)

Your capability tier depends on which tools are installed and working on your machine. Forge, Forge+, and Deep all need ast-grep, and Forge+ and Deep each add different tools on top of it. Deep does not need cocoindex-code, so it does not build on Forge+:

- **Quick:** No extra tools required. SKF reads source files and builds best-effort skills. Works in under a minute. GitHub CLI used when available.
- **Forge:** Adds [ast-grep](https://ast-grep.github.io). SKF uses AST parsing to verify instructions against the actual code structure.
- **Forge+:** Adds [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code). SKF searches the code by meaning to find the most relevant source regions before AST extraction, which improves coverage on large codebases.
- **Deep:** The full pipeline. Needs [ast-grep](https://ast-grep.github.io), the [GitHub CLI](https://cli.github.com), and [QMD](https://github.com/tobi/qmd), all three, with QMD running. SKF indexes the project's issues, pull requests, changelogs, and docs so it can search them, and it explores the GitHub repository. Skills gain historical context and deprecation warnings. cocoindex-code is optional here; adding it to Deep also brings its semantic code search, which gives the most capability.

You don't need all tools to start. When you run Setup Forge (`@Ferris SF`), SKF checks which tools work and sets your tier from that. If you install a tool later, run `@Ferris SF` again to update your tier. See [Skill Model → Progressive Capability Model](/docs/skill-model.md#progressive-capability-model) for the full technical treatment.

---

## Drift

Drift happens when the source code changes but the skill instructions haven't been updated to match. A skill might still reference a function that was renamed, removed, or had its signature changed upstream.

SKF detects drift by comparing the skill's recorded provenance against the current code. The Audit Skill workflow (`@Ferris AS`) scans for these mismatches in both single-library skills and stack skills (one skill that covers several libraries a project uses together). A stack built from source code is checked library by library. A stack assembled from skills you already have is checked for member skills that changed after it was assembled.

Audit Skill also checks the documentation pages a skill tracked when it was built, and reports which of them changed upstream since then. This check is informational and does not change the drift score.

**Example:** Your skill says `createUser(name: string)` but the function was renamed to `registerUser(name: string, email: string)` in the last release. That's drift. For a stack assembled from existing skills, constituent drift means one of its member skills was updated after the stack was assembled, and the stack hasn't been rebuilt to pick up the change.

---

## Version Pinning

Every skill records the exact version (or commit) of the source code it was built from. This means you always know which version of the library the instructions apply to.

By default, the version is auto-detected from the source (package.json, pyproject.toml, etc.). You can also target a specific version, either by giving it during `@Ferris BS` (Brief Skill) or by adding `@version` to a Quick Skill command (`@Ferris QS cognee@1.0.0`). This is especially useful for docs-only skills, where there is no source code to detect a version from. When you target a version on a remote repository, SKF finds the matching git tag and clones from it. That way the extracted API signatures come from that version's code, not from whatever is on the default branch with a label added. If no tag matches, Quick Skill stops and lists the tags it found, while Create Skill warns you and falls back to the default branch.

When the source updates, re-run `@Ferris US` (Update Skill) to regenerate the skill. SKF writes the result as a new version and leaves the old one in place. Anything you wrote between `<!-- [MANUAL:name] -->` and `<!-- [/MANUAL:name] -->` markers is carried over; edits made anywhere else are not protected and can be overwritten. Update Skill follows the ref the skill was built from, so a skill built from a branch picks up that branch's new commits. To move a skill built from a release tag to a newer release, run `@Ferris US <name> --target-ref <tag>`.

---

## BMAD Module

SKF is a plugin (called a "module") for [BMAD Method](https://docs.bmad-method.org/), a framework for running structured AI workflows. You don't need to know BMAD to use SKF. The standalone installer (`npx bmad-module-skill-forge install`) sets everything up.

If you already use BMAD, see [BMAD Synergy](/docs/bmad-synergy.md) for how SKF workflows fit into BMAD's main four-phase workflow (BMM) and optional modules such as TEA (Test Architect), BMB (BMAD Builder), and GDS (Game Dev Studio).
