---
title: Forge-Auto
description: Zero-ceremony skill creation. One command turns a GitHub repo (optionally pinned to a version) or a documentation URL into a verified skill
---

Forge-Auto turns a library's repo or documentation site into a verified skill with one command. Under the hood it is a [pipeline alias](/docs/workflows.md#pipeline-aliases): a short name that runs five workflows in a row. You write no brief and make no scope decisions, and a typical run takes about 3 to 5 minutes.

If you're new to SKF and want to try it without reading anything else, start here. Do one thing first: after installing SKF, run `@Ferris SF` once so SKF can detect your tools and set your forge tier (Quick, Forge, Forge+ or Deep). Without it, the first stage stops and asks you to run setup.

---

## Invocation

Two kinds of target, one command pattern. The lines below are a repo URL, a doc URL (docs-only), and a repo URL pinned to a version:

```
@Ferris forge-auto https://github.com/honojs/hono
@Ferris forge-auto https://docs.example.com
@Ferris forge-auto https://github.com/honojs/hono --pin v4.6.0
```

- **Repo URL**: analyzes the source repository (GitHub, GitLab or Bitbucket), extracts its exports, and compiles a skill from code and docs. A path to a folder on your machine works the same way.
- **Doc URL**: any other `http://` or `https://` address. SKF skips source analysis and builds the skill from the documentation alone, naming it after the site (`docs.example.com` becomes `docs-example-com`). Useful for closed-source libraries or when the docs are the canonical reference.
- **`--pin <version>`**: add it to a GitHub repo URL to target a specific release tag or branch, so the skill is locked to that exact API surface. SKF checks the pin with the GitHub CLI (`gh`), so `gh` must be installed, and it stops if no tag or branch matches. Without `--pin`, SKF pins a GitHub repo to its latest release tag, and otherwise uses the latest commit. A doc URL ignores `--pin`.

---

## Pipeline Stages

forge-auto expands to `AN[auto] BS[auto] CS TS[min:90] EX`. The `[auto]` flag on the two analysis stages (AN, BS) swaps their question-and-answer steps for automatic scoping and briefing. Like every pipeline, forge-auto also runs all five stages in [headless mode](/docs/workflows.md#headless-mode), so no stage stops to ask you anything: each confirmation takes its default answer. The compile, test, and export stages run their usual steps once the analysis context is ready.

| Stage | Workflow | Mode | What Happens |
|-------|----------|------|-------------|
| 1 | **Analyze Source** (AN) | `[auto]` | Scans the target, detects its shape (`library-API`, `reference-app`, `language-reference` or `stack-compose`), counts its exports, and writes a scope and brief automatically. If the shape is `unknown`, or the repo has no package manifest or language signal SKF can read, AN switches to its full step-by-step analysis instead. |
| 2 | **Brief Skill** (BS) | `[auto]` | Enriches the auto-generated brief with doc detection results. No interactive scoping: the brief is assembled from AN's output. |
| 3 | **Create Skill** (CS) | standard | Compiles the skill from the enriched brief. Extracts exports, resolves documentation sources, validates structure. |
| 4 | **Test Skill** (TS) | `[min:90]` | Verifies completeness against a **90% quality threshold** (stricter than the default 80%). A score of at least 80% but under 90% still passes, with an evidence report on what kept it under 90%. A score below 80% fails and stops the pipeline before export. |
| 5 | **Export Skill** (EX) | standard | Validates the package, generates context snippets, and injects into your IDE's context file. |

Data flows automatically between stages: the brief path from AN feeds BS, the skill name from CS feeds TS, and so on. See [Pipeline Mode](/docs/workflows.md#pipeline-mode) for the general mechanics.

---

## Automatic Behaviors

forge-auto's `[auto]` flags activate several behaviors that normally require manual input:

- **Auto-scope**: shape detection (`library-API`, `reference-app`, `language-reference`, `stack-compose`) decides the scope, and each shape maps to one of three scope types in the brief: `full-library`, `public-api` (a library with more than 200 exports), or `reference-app`. No interactive scope confirmation.
- **Auto-brief**: the brief is generated and enriched with doc-detection results in one pass, without the interactive discovery flow that `BS` uses standalone.
- **Coexistence detection**: if a skill with the same source or name already exists, forge-auto leaves it untouched and creates the new skill beside it under a new name ending in `-wiki` (for example `hono-wiki`). The new skill is separate, not a new version of the old one. forge-auto makes this choice for you, because pipelines run without prompts.
- **Auto-decomposition**: a monorepo with more than 3 packages is a *decomposition candidate*, meaning it could become several skills. A cohesion check then decides whether to merge it into one skill (the usual outcome, since most published monorepos hang together) or split it into one skill per package. When in doubt it merges. A single package with a very large API is never split: it stays one skill, and create-skill moves the detail into `references/` files.
- **Language-reference handling**: when the repo is a compiler, interpreter, or parser, AN classifies it as a `language-reference`. For a whole language (a compiler or interpreter), the useful content is the language's guide and standard-library docs, not the compiler's internals, so AN adds links to the language's official docs to the brief. If it finds none, the analysis report marks the skill **DEGRADED**: built from code alone, it has little value until you add the guide and standard-library docs. The report suggests enriching the skill with `US`, or running forge-auto on the docs' URL, which builds a separate docs-only skill.

---

## Expected Output

A successful forge-auto run writes a complete skill package to your skills folder (`skills/<name>/<version>/<name>/` by default), then exports it, ready for use. The package includes:

- `SKILL.md`: the compiled skill, where each instruction cites the source it came from
- `references/`: detail files, one per group of functions or types
- `metadata.json`: version, source, and how many exports landed in each confidence tier
- `context-snippet.md`: a short index of the skill, which export adds to your IDE's context file (CLAUDE.md, AGENTS.md or .cursorrules)

The working files (the brief, the test report and the evidence report) stay in your forge data folder (`forge-data/<name>/` by default). To install the skill in your project, run the `npx skills add ./skills/...` command that export prints.

The quality threshold is 90%. A skill that scores at least 80% but under 90% still passes and is exported, and SKF writes `evidence-report-fallback.md` next to the test report (in `forge-data/<name>/<version>/`) listing the findings that kept it under 90%. The pipeline goes on to export only when Test Skill settles a PASS. A skill that scores below 80% fails: the pipeline stops at TS, before export, and the test report's gap report lists what is missing. Every other verdict but PASS stops it there too: a FAIL that a cap forced although the score clears 90%, INCONCLUSIVE (Test Skill had too little evidence to grade the skill) and pass-with-drift. Any Critical or High gap, such as a wrong or fabricated signature, also stops the pipeline at TS, before a score is computed: Test Skill lists each blocking gap, and the test report's Gap Report puts them first. A missing export is a Medium gap, so it lowers the score and blocks nothing on its own. To fix the gaps, run `@Ferris US <name> --from-test-report`, then `@Ferris TS[<name>] EX` to re-test and export (the brackets give Test Skill the skill's name). That chain has no alias, so Test Skill re-tests it at the default 80% bar. The next time you start Ferris, he offers that repair route himself, at the recorded 90% threshold: accept his offer to keep forge-auto's 90%, or run `@Ferris TS <name> --threshold=90`, then `@Ferris EX <name>`. A plain `@Ferris US <name>` also finds a failed or pass-with-drift test report that is newer than the skill and that no repair has applied, and offers to repair its gaps (`[G]`) or check the source (`[S]`); a headless run checks the source and adds an `unconsumed-test-report` warning.

---

## Timing

A typical library (50–200 exports) takes **3–5 minutes** end to end. Factors that increase time:

- Multi-package monorepos (>3 packages) flag a decomposition candidate; if the cohesion check splits the repo into N skills, add 1–3 minutes
- Doc-only targets depend on documentation site size and structure
- The Deep tier (ast-grep, the GitHub CLI and QMD all installed) spends more time on enrichment

---

## Migration from `deepwiki` and `onboard`

This pipeline was briefly named `deepwiki`. It was renamed to **`forge-auto`** to avoid confusion with the [DeepWiki MCP](https://deepwiki.com): `forge-auto` compiles a verified skill from source and **does not** call that MCP or ingest a generated wiki. `deepwiki` still works as a **deprecated alias** (it resolves to `forge-auto` and prints a one-time notice); prefer `forge-auto` going forward.

Before that, the auto pipeline replaced the older `onboard` alias. `onboard` has been removed: running it returns an error directing you to `forge-auto`. The key differences from `onboard`: it ran `AN CS TS EX` at an 80% quality threshold, whereas `forge-auto` adds auto-scope, auto-brief, a higher quality target (90% vs 80%), and accepts doc URLs as well as repo URLs and local project paths.

---

## Related

- [Workflows](/docs/workflows.md): pipeline mode mechanics, headless mode, circuit breakers
- [Concepts](/docs/concepts.md): provenance, confidence tiers, drift, version pinning
- [BMAD Synergy](/docs/bmad-synergy.md): how forge-auto fits into BMAD phases, and standalone SKF usage
