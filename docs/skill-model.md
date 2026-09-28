---
title: Skill Model
description: What a Skill Forge skill contains, from progressive capability tiers and the confidence model to output architecture, the dual-output strategy and the ownership model.
---

A Skill Forge skill is more than a single markdown file. This page explains what ships when you compile and export a skill: the capability tier your forge runs at, the confidence level of every claim, the files in the output directory, and why every skill is shipped as both an active instruction manual and a passive context index. For a walkthrough of compilation, see [How It Works](/docs/how-it-works.md). For the audit recipe that ties this all together, see [Verifying a Skill](/docs/verifying-a-skill.md).

---

## Progressive Capability Model

SKF uses an additive tier model. You never lose capability by adding a tool.

| Tier | Required Tools | What You Get |
|------|---------------|-------------|
| **Quick** | None (`gh_bridge` and `skill-check` used when available; `tessl` when you opt in to Tessl Review) | Source reading + spec validation. Best-effort skills in under a minute. **Note:** Quick Skill (QS) ignores your tier on purpose. It always reads source without ast-grep and records `confidence_tier: Quick` and `source_authority: community`, whatever tools you have installed. It never runs Tessl Review. |
| **Forge** | + `ast_bridge` (ast-grep) | Structural truth. AST-verified signatures. Co-import detection. T1 confidence. |
| **Forge+** | + `ccc_bridge` (cocoindex-code) | Semantic discovery. CCC pre-ranks files by meaning before AST extraction. Better coverage on large codebases. |
| **Deep** | `ast_bridge` + `gh_bridge` (gh) + `qmd_bridge` (QMD). CCC is optional and adds semantic discovery when installed. | Knowledge search. Temporal provenance (issue, PR and changelog history). Audit Skill adds QMD semantic comparison to its drift checks. Full intelligence. |

Setup detects your installed tools and sets your tier automatically:

```
@Ferris SF
```

```
═══════════════════════════════════════
  FORGE STATUS
═══════════════════════════════════════

  Tier:  Deep
  Deep tier active. Full capability unlocked: AST-backed code analysis,
  GitHub repository exploration, and QMD knowledge search with
  cross-repository synthesis. Maximum provenance and intelligence.

  Tools Detected:
  - ast-grep 0.42.0
  - gh 2.91.0 (2026-04-22)
  - qmd 2.0.1
  - ccc (daemon healthy)

  QMD Registry:
  0 collection(s) healthy
  23 orphaned collection(s) kept

  CCC Index:
  indexed this run, semantic discovery ready (1 file)

  Files written this run:
  - forge-tier.yaml: {project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml
  - {project-root}/forge-data/ (directory ensured)
  - .cocoindex_code/settings.yml: {project-root}/.cocoindex_code/settings.yml (6 SKF exclusion patterns merged)
  - .gitignore: {project-root}/.gitignore (`/.cocoindex_code/` added by `ccc init`)
  - .cocoindex_code/ ccc index: 1 file indexed

═══════════════════════════════════════
  Forge ready. Deep tier active.
═══════════════════════════════════════

Health Check: Clean run. No workflow issues to report.

Workflow complete.
```

Setup then suggests where to go next: `@Ferris forge-auto <repo-or-doc-url>` briefs, compiles, tests and exports a skill in one command; `/skf-brief-skill` lets you scope a skill by hand; `/skf-quick-skill` is a fast template-driven path; and `/skf-audit-skill` checks a skill you already have against its current source.

Don't have ast-grep, cocoindex-code, or QMD yet? That's fine. Quick tier works with no extra tools, and the GitHub CLI (`gh`), if you have it, helps it read remote source. When you install a tool later, run `@Ferris SF` again: setup detects it and raises your tier.

### Tier Override: Comparing Output Across Tiers

You can force a specific tier by setting `tier_override` in your preferences file (`_bmad/_memory/forger-sidecar/preferences.yaml`):

```yaml
# Force Forge tier regardless of detected tools
tier_override: Forge
```

This is useful for comparing skill quality across tiers for the same target. Each recompile writes into the same version folder and replaces the previous run's files, so commit or copy the skill folder before you switch tiers:

```
# 1. Set tier_override: Quick in preferences.yaml
@Ferris CS                # compile at Quick tier

# 2. Change to tier_override: Forge
@Ferris CS                # recompile at Forge tier, then compare output

# 3. Change to tier_override: Forge+
@Ferris CS                # recompile with semantic discovery, then compare coverage

# 4. Reset to tier_override: ~ (auto-detect)
```

Set `tier_override` to `Quick`, `Forge`, `Forge+`, or `Deep` (capital letters matter). Set it to `~` (null) to return to auto-detection. Setup (SF) and every tier-aware workflow respect it: Analyze Source (AN), Brief Skill (BS), Create Skill (CS), Stack Skill (SS), Update Skill (US), Audit Skill (AS) and Test Skill (TS). Quick Skill (QS) ignores it. SKF ignores a value it does not recognize and uses the detected tier. You can force a tier your tools do not support, but setup warns you, and steps that need a missing tool then stop or fall back to a lower tier with a warning.

---

## Confidence Tiers

Every claim in a generated skill carries a confidence tier that traces to its source:

| Tier | Source | Tool | What It Means |
|------|--------|------|---------------|
| **T1** | AST extraction | `ast_bridge` | Current code, structurally verified. Immutable for that version. |
| **T1-low** | Source reading | Source reading (no ast-grep) | Read from source without AST verification. Produced by Quick tier, and by Forge, Forge+ and Deep when ast-grep cannot parse a file or a remote source cannot be cloned. Location correct, signature may be inferred. |
| **T2** | QMD evidence | `qmd_bridge` | Historical + planned context (issues, PRs, changelogs, docs). |
| **T3** | External documentation | `doc_fetcher` | External and untrusted, so SKF keeps it apart: a T3 claim keeps its `[EXT:...]` label and never overrides a T1, T1-low or T2 claim. |

### Temporal Provenance

Confidence tiers map to temporal scopes:

- **T1-now (instructions):** What ast-grep sees in the checked-out code. This is what your agent executes.
- **T2-past (annotations):** Closed issues, merged PRs and changelogs that explain why the API looks the way it does.
- **T2-future (annotations):** Open PRs, deprecation warnings and RFCs that show what's coming.

Progressive disclosure controls how much context surfaces at each level:

| Output | Content |
|--------|---------|
| `context-snippet.md` | T1-now + T2-future gotchas (breaking changes, deprecation warnings), compressed and always on |
| `SKILL.md` | T1-now, plus T2-future migration and deprecation warnings (Deep tier only) |
| `references/` | Full temporal context with all tiers |

### Tier and Authority

Your forge tier sets how strong a skill's accuracy guarantee can be:

| Forge Tier | AST? | CCC? | QMD? | Accuracy Guarantee |
|-----------|------|------|------|-------------------|
| Quick | No | No | No | Best-effort |
| Forge | Yes | No | No | Structural (AST-verified) |
| Forge+ | Yes | Yes | No | Structural + semantic discovery |
| Deep | Yes | Optional (adds semantic discovery) | Yes | Full (structural + contextual + temporal) |

**Tier and authority are separate.** Tier says how deeply SKF could check the code. Authority (`source_authority`) says who stands behind the skill, and it comes from your brief, not from your tools. Brief Skill asks whether you maintain the library: a maintainer gets `official`, a private or company codebase gets `internal`, and everyone else gets `community`, the default. In a headless run where you do not set it, SKF picks `official` only when your GitHub login matches the repo owner. Quick Skill and docs-only skills are always `community`. Only library maintainers should publish `official` skills to the [agentskills.io](https://agentskills.io) open-format ecosystem, so a Deep-tier skill compiled by a third party stays `community`. See [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills), where all four Deep-tier skills ship as `community` by design: audited, not blessed.

---

## Completeness Scoring

Skills are graded on a 0–100 completeness scale. See [how the score is computed](/docs/verifying-a-skill.md#how-the-score-is-computed) in Verifying a Skill for the formula and tier adjustments.

---

## Output Architecture

### Per-Skill Output

Every generated skill produces a self-contained, version-aware directory:

```
skills/{name}/
├── active -> {version}           # Symlink to current version
├── {version}/
│   └── {name}/                   # agentskills.io-compliant package
│       ├── SKILL.md              # Active skill (loaded on trigger)
│       ├── context-snippet.md    # Passive context (compressed, always-on)
│       ├── metadata.json         # Machine-readable provenance
│       ├── references/           # Progressive disclosure
│       │   ├── {function-a}.md
│       │   └── {function-b}.md
│       ├── scripts/              # Executable automation (when detected in source)
│       │   └── {script-name}.sh
│       └── assets/               # Templates, schemas, configs (when detected in source)
│           └── {asset-name}.json
└── {older-version}/
    └── {name}/                   # Previous version preserved
        └── ...
```

Multiple versions coexist under the same skill name. The `active` symlink points to the current version. Updating a skill for a new library release creates a new version directory, so users pinned to older versions keep their skill intact. The inner `{name}/` directory is a standalone [agentskills.io](https://agentskills.io) package, directly installable via `npx skills add`.

The `scripts/` and `assets/` directories are optional. SKF creates them only when the source repository contains executable scripts or static assets that match its detection rules. Each file traces to its source via `[SRC:file:L1]` provenance citations with SHA-256 content hashes for drift detection. User-authored files go in `scripts/[MANUAL]/` or `assets/[MANUAL]/` subdirectories and are preserved during updates.

SKF also keeps workspace files for each version outside the skill package, in `forge-data/{name}/{version}/` by default: `provenance-map.json` (where each documented symbol came from), `evidence-report.md`, `extraction-rules.yaml` and test reports. The brief, `skill-brief.yaml`, sits one level up in `forge-data/{name}/`. These files are not part of the installable package; see [Verifying a Skill](/docs/verifying-a-skill.md) for how to use them.

### SKILL.md Format

Skills follow the [agentskills.io specification](https://agentskills.io/specification) with frontmatter:

```yaml
---
name: oms-cognee
description: >
  Builds apps on top of cognee v1.0.0, the knowledge-graph memory engine for AI agents.
  Use when ingesting text/files/URLs into persistent memory, building knowledge graphs,
  searching graph-backed memory with multiple SearchType modes, enriching graphs with
  memify/improve, scoping memory with datasets and node_sets, configuring LLM/embedding/
  graph/vector backends, running custom task pipelines, tracing operations, decorating
  agent entrypoints with `agent_memory`, connecting to Cognee Cloud with `serve`, or
  visualizing the graph. Covers cognee/__init__.py exports: the V1 API (add, cognify,
  search, memify, datasets, prune, update, run_custom_pipeline, config, SearchType,
  visualize_graph, pipelines, Drop, run_startup_migrations, tracing) and the V2
  memory-oriented API (remember, RememberResult, recall, improve, forget, serve,
  disconnect, visualize, agent_memory). Do NOT use for: cognee internals, the HTTP
  REST API (use cognee-mcp or the FastAPI server), non-cognee memory/RAG libraries.
---
```

Every instruction in the body traces to source:

```python
await cognee.search(  # [AST:cognee/api/v1/search/search.py:L27]
    query_text="What does Cognee do?"
)
```

### metadata.json: The Birth Certificate

Machine-readable provenance for every skill:

This is a trimmed excerpt from the real [`oms-cognee/1.0.0/metadata.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/oms-cognee/1.0.0/oms-cognee/metadata.json) shipped with the oh-my-skills canonical output. Every value below is copied from the file, not made up for illustration.

```json
{
  "name": "oms-cognee",
  "version": "1.0.0",
  "skill_type": "single",
  "source_authority": "community",
  "source_repo": "https://github.com/topoteretes/cognee",
  "source_commit": "3c048aa4",
  "source_ref": "v1.0.0",
  "confidence_tier": "Deep",
  "spec_version": "1.3",
  "generation_date": "2026-04-13T00:00:00Z",
  "language": "python",
  "ast_node_count": 34,
  "confidence_distribution": {
    "t1": 34,
    "t1_low": 0,
    "t2": 11,
    "t3": 15
  },
  "stats": {
    "exports_documented": 34,
    "exports_public_api": 34,
    "exports_internal": 0,
    "exports_total": 34,
    "public_api_coverage": 1.0,
    "total_coverage": 1.0
  }
}
```

Fields omitted from this excerpt for brevity: `source_root`, `description`, `exports[]`, `tool_versions`, `dependencies`, `compatibility`, `last_update`, `generated_by`. The full 93-line file lives at [`oh-my-skills/skills/oms-cognee/1.0.0/oms-cognee/metadata.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/oms-cognee/1.0.0/oms-cognee/metadata.json).

Two fields are easy to mix up. `confidence_tier` holds the forge tier the skill was compiled at (Quick, Forge, Forge+ or Deep). `confidence_distribution` counts the claims at each confidence tier (T1, T1-low, T2, T3).

`scripts` and `assets` arrays are optional: SKF leaves them out entirely, rather than writing empty arrays, when the source has no scripts or assets.

### Stack Skill Output

Stack skills map how your dependencies interact: shared types, co-import patterns and integration points.

```
skills/{project}-stack/
├── active -> {version}
└── {version}/
    └── {project}-stack/
        ├── SKILL.md              # Integration patterns + project conventions
        ├── context-snippet.md    # Compressed stack index
        ├── metadata.json         # Component versions, integration graph
        └── references/
            ├── nextjs.md         # Project-specific subset
            ├── better-auth.md    # Project-specific subset
            └── integrations/
                ├── auth-db.md    # Cross-library pattern
                └── pwa-auth.md   # Cross-library pattern
```

In code-mode, the source is your project repo: SKF reads your dependency manifests and finds where libraries are imported together, and component references trace to library repos. In compose-mode, when there is no code yet, SKF builds the stack skill from skills you already compiled plus your architecture document, and labels any integration it infers. Either way, `metadata.json` records `skill_type: "stack"`.

---

## Dual-Output Strategy

Every skill SKF compiles ships as **two** files on purpose, and the reason is empirical, not aesthetic.

> **[Vercel research](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals):** a compressed docs index in passive context (`AGENTS.md`) reached a **100% pass rate** in Vercel's agent evals. Skills peaked at **79%**, and only when the agent was told explicitly to use them; left to decide on its own, the agent gained nothing from the skill over having no docs at all (53%). The dual-output strategy is built to close that 21-point gap.

Every skill generates both:

1. **`SKILL.md`**: the active skill, loaded on trigger with the full instruction set. This is the instruction manual your agent opens when it knows it needs library guidance.
2. **`context-snippet.md`**: passive context, compressed to about 80 to 120 tokens per skill (a Deep-tier skill whose gotchas carry breaking changes can run longer). Only `export-skill` injects it into platform context files (`CLAUDE.md` / `AGENTS.md` / `.cursorrules`). This is the ambient index that tells your agent the skill exists in the first place and should be opened for relevant work.

If you do not want SKF to touch those files, set `passive_context: false` in your preferences file (`_bmad/_memory/forger-sidecar/preferences.yaml`). Export then skips the snippet and the managed section.

Without the snippet, the agent has to decide on its own that a skill is relevant, and it often skips `SKILL.md`. Without `SKILL.md`, the snippet has nothing to point at. **Both halves are load-bearing.**

### Managed Context Section

Export injects a managed section between markers:

The block below is the real managed section currently in [`oh-my-skills/CLAUDE.md`](https://github.com/armelhbobdad/oh-my-skills/blob/main/CLAUDE.md), showing one of its four compiled skills. Every line is copied from the file except the last one before `<!-- SKF:END -->`, which stands in for the three skills left out:

```markdown
<!-- SKF:BEGIN updated:2026-04-25 -->
[SKF Skills]|4 skills|0 stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|[oms-cognee v1.0.0]|root: skills/oms-cognee/
|IMPORTANT: oms-cognee v1.0.0 — read SKILL.md before writing cognee code. Do NOT rely on training data.
|quick-start:SKILL.md#quick-start
|api-v1: add(), cognify(), search(), memify(), update(), run_custom_pipeline(), visualize_graph(), datasets, prune, config, SearchType, pipelines, Drop, run_startup_migrations(), session, tracing
|api-v2: remember()→RememberResult, recall(), improve(), forget(), serve()/disconnect(), visualize(), @agent_memory
|key-types:SKILL.md#key-types — SearchType: GRAPH_COMPLETION (default), RAG_COMPLETION, CHUNKS, CHUNKS_LEXICAL, SUMMARIES, TEMPORAL, CODING_RULES, CYPHER, FEELING_LUCKY, GRAPH_COMPLETION_DECOMPOSITION (+5 more); Task, Drop, RememberResult, DataPoint, 5 Cognee* exceptions
|gotchas: cognee.low_level REMOVED from public API in v1.0.0 (import from cognee.infrastructure.engine directly); cognee.run_migrations REPLACED by cognee.run_startup_migrations (relational + vector); cognee.delete is DEPRECATED since v0.3.9 (use cognee.datasets.delete_data or cognee.forget); cognee.pipelines restructured in v1.0.0 (package with Drop + lazy re-exports); cognee.agent_memory requires async function; cognee.serve() without url triggers Auth0 Device Code Flow; cognee.start_ui is sync and needs pid_callback arg; all add/cognify/search/memify/remember/recall/improve/forget/serve are async — always await.
|
|(three more skills are left out here for brevity: oms-cocoindex, oms-storybook-react-vite and oms-uitripled; see the full file)
<!-- SKF:END -->
```

A snippet aims for about 80 to 120 tokens per skill: the version, an instruction to read `SKILL.md`, section anchors and inline gotchas. A Deep-tier skill whose gotchas carry breaking changes can run longer, like the cognee entry above. Root paths are per-IDE: each of the 23 supported IDEs has its own skill directory (for example `.claude/skills/`, `.cursor/skills/`, `.github/skills/`, `.windsurf/skills/`). A repo that keeps all its skills in one shared folder can set `snippet_skill_root_override` in its SKF `config.yaml` instead, which is why the oh-my-skills root paths start with `skills/`. See [`skf-export-skill/assets/managed-section-format.md`](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-export-skill/assets/managed-section-format.md) for the complete mapping from IDE to context file. The format follows [Vercel's research](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) finding that an index with explicit retrieval instructions greatly improves agent performance. You decide where the section sits in the file; Ferris decides what goes between the markers. Create Skill and Update Skill also write `context-snippet.md`, but only as a draft inside the skill folder, and they never touch the managed section. Only `export-skill` adds a skill there, and an `.export-manifest.json` file records which skills you have exported, so drafts never leak into the managed section.

---

## Ownership Model

| Context | `source_authority` | Distribution |
|---------|-------------------|-------------|
| OSS library (maintainer generates) | `official` | `npx skills publish` to agentskills ecosystem |
| Internal service (team generates) | `internal` | `skills/` in repo, ships with code |
| External dependency (consumer generates) | `community` | Local `skills/`, marked as community |

Provenance maps enable verification: an `official` skill's provenance must trace to the actual source repo owned by the author.
