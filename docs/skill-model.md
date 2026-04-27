---
title: Skill Model
description: What a Skill Forge skill contains — progressive capability tiers, confidence model, output architecture, the dual-output strategy, and the ownership model.
---

A Skill Forge skill is more than a single markdown file. This page explains what ships when you compile and export a skill: the capability tier your forge runs at, the confidence level of every claim, the files in the output directory, and why every skill is shipped as both an active instruction manual and a passive context index. For a walkthrough of compilation, see [How It Works](../how-it-works/). For the audit recipe that ties this all together, see [Verifying a Skill](../verifying-a-skill/).

---

## Progressive Capability Model

SKF uses an additive tier model. You never lose capability by adding a tool.

| Tier | Required Tools | What You Get |
|------|---------------|-------------|
| **Quick** | None (`gh_bridge`, `skill-check`, `tessl` used when available) | Source reading + spec validation + content quality review. Best-effort skills in under a minute. **Note:** Quick Skill (QS) is tier-unaware by design — it always runs at community tier regardless of installed tools. |
| **Forge** | + `ast_bridge` (ast-grep) | Structural truth. AST-verified signatures. Co-import detection. T1 confidence. |
| **Forge+** | + `ccc_bridge` (cocoindex-code) | Semantic discovery. CCC pre-ranks files by meaning before AST extraction. Better coverage on large codebases. |
| **Deep** | `ast_bridge` + `gh_bridge` (gh) + `qmd_bridge` (QMD). CCC optional — enhances when installed. | Knowledge search. Temporal provenance. Drift detection. Full intelligence. |

Setup detects your installed tools and sets your tier automatically:

```
@Ferris SF
```

```
═══════════════════════════════════════
  FORGE STATUS
═══════════════════════════════════════

  Tier:  Deep
  Deep tier active. Full capability unlocked — AST-backed code analysis,
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
  indexed this run — semantic discovery ready (1 file)

  Files written this run:
  - forge-tier.yaml — {project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml
  - .cocoindex_code/settings.yml — {project-root}/.cocoindex_code/settings.yml (6 SKF exclusion patterns merged)
  - .cocoindex_code/ ccc index — 1 file indexed

═══════════════════════════════════════
  Forge ready. Deep tier active.
═══════════════════════════════════════

  Next: try [BS] Brief Skill to scope your first compilation target,
  or [QS] Quick Skill for a fast template-driven path.
  Already have a skill? [AS] Audit Skill drift-checks an existing skill
  against current sources.

Health Check: Clean run. No workflow issues to report.

Workflow complete.
```

Don't have ast-grep, cocoindex-code, or QMD yet? No problem — Quick mode works with no additional tools. Optional GitHub CLI improves source access. Install tools later; your tier upgrades automatically.

### Tier Override — Comparing Output Across Tiers

You can force a specific tier by setting `tier_override` in your preferences file (`_bmad/_memory/forger-sidecar/preferences.yaml`):

```yaml
# Force Forge tier regardless of detected tools
tier_override: Forge
```

This is useful for comparing skill quality across tiers for the same target:

```
# 1. Set tier_override: Quick in preferences.yaml
@Ferris CS                # compile at Quick tier

# 2. Change to tier_override: Forge
@Ferris CS                # recompile at Forge tier — compare output

# 3. Change to tier_override: Forge+
@Ferris CS                # recompile with semantic discovery — compare coverage

# 4. Reset to tier_override: ~ (auto-detect)
```

Set `tier_override` to `Quick`, `Forge`, `Forge+`, or `Deep`. Set to `~` (null) to return to auto-detection. The override is respected by all tier-aware workflows (CS, SS, US, AS, TS).

---

## Confidence Tiers

Every claim in a generated skill carries a confidence tier that traces to its source:

| Tier | Source | Tool | What It Means |
|------|--------|------|---------------|
| **T1** | AST extraction | `ast_bridge` | Current code, structurally verified. Immutable for that version. |
| **T1-low** | Source reading | `ast_bridge` (fallback) | Source-read without AST verification. Produced by Quick tier and by Forge/Forge+/Deep when ast-grep cannot parse a specific file. Location correct, signature may be inferred. |
| **T2** | QMD evidence | `qmd_bridge` | Historical + planned context (issues, PRs, changelogs, docs). |
| **T3** | External documentation | `doc_fetcher` | External, untrusted. Quarantined. |

### Temporal Provenance

Confidence tiers map to temporal scopes:

- **T1-now (instructions):** What ast-grep sees in the checked-out code. This is what your agent executes.
- **T2-past (annotations):** Closed issues, merged PRs, changelogs — why the API looks the way it does.
- **T2-future (annotations):** Open PRs, deprecation warnings, RFCs — what's coming.

Progressive disclosure controls how much context surfaces at each level:

| Output | Content |
|--------|---------|
| `context-snippet.md` | T1-now + T2-future gotchas (breaking changes, deprecation warnings) — compressed, always-on |
| `SKILL.md` | T1-now + lightweight T2 annotations |
| `references/` | Full temporal context with all tiers |

### Tier Constrains Authority

Your forge tier limits what authority claims a skill can make:

| Forge Tier | AST? | CCC? | QMD? | Max Authority | Accuracy Guarantee |
|-----------|------|------|------|---------------|-------------------|
| Quick | No | No | No | `community` | Best-effort |
| Forge | Yes | No | No | `official` | Structural (AST-verified) |
| Forge+ | Yes | Yes | No | `official` | Structural + semantic discovery |
| Deep | Yes | opt. (enhances when installed) | Yes | `official` | Full (structural + contextual + temporal) |

**Tier governs technical verification; authority is an ecosystem claim.** Reaching Deep tier unlocks the *capability* to claim `official` authority — it does not grant it. Only library maintainers can publish `source_authority: official` skills via the [agentskills.io](https://agentskills.io) open-format ecosystem. A Deep-tier skill compiled by a third party is `community` by default. See [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills), where all four Deep-tier skills ship as `community` by design — audited, not blessed.

---

## Completeness Scoring

Skills are graded on a 0–100 completeness scale. See [how the score is computed](../verifying-a-skill/#how-the-score-is-computed) in Verifying a Skill for the formula and tier adjustments.

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

Multiple versions coexist under the same skill name. The `active` symlink points to the current version. Updating a skill for a new library release creates a new version directory — users pinned to older versions keep their skill intact. The inner `{name}/` directory is a standalone [agentskills.io](https://agentskills.io) package, directly installable via `npx skills add`.

The `scripts/` and `assets/` directories are optional — only created when the source repository contains executable scripts or static assets matching detection heuristics. Each file traces to its source via `[SRC:file:L1]` provenance citations with SHA-256 content hashes for drift detection. User-authored files go in `scripts/[MANUAL]/` or `assets/[MANUAL]/` subdirectories and are preserved during updates.

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
await cognee.search(  # [AST:cognee/api/v1/search/search.py:L26]
    query_text="What does Cognee do?"
)
```

### metadata.json — The Birth Certificate

Machine-readable provenance for every skill:

This is a trimmed excerpt from the real [`oms-cognee/1.0.0/metadata.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/oms-cognee/1.0.0/oms-cognee/metadata.json) shipped with the oh-my-skills canonical output. Every value below is verbatim from the file — not illustrative.

```json
{
  "name": "oms-cognee",
  "version": "1.0.0",
  "skill_type": "single",
  "source_authority": "community",
  "source_repo": "https://github.com/topoteretes/cognee",
  "source_commit": "3c048aa4147776f14d4546704f986242554a9ef3",
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

Fields omitted from this excerpt for brevity: `description`, `exports[]`, `tool_versions`, `dependencies`, `compatibility`, `last_update`, `generated_by`. The full 93-line file lives at [`oh-my-skills/skills/oms-cognee/1.0.0/oms-cognee/metadata.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/skills/oms-cognee/1.0.0/oms-cognee/metadata.json).

`scripts` and `assets` arrays are optional — omitted entirely (not empty) when the source has no scripts or assets.

### Stack Skill Output

Stack skills map how your dependencies interact — shared types, co-import patterns, integration points:

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

The primary source is your project repo. Component references trace to library repos. `skill_type: "stack"` in metadata.

---

## Dual-Output Strategy

Every skill SKF compiles ships as **two** files on purpose — and the reason is empirical, not aesthetic.

> **[Vercel research](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals):** passive context (`AGENTS.md` / `CLAUDE.md`) achieves a **100% pass rate** in agent evals. Active skills loaded alone achieve **79%**. The 21-point gap is what the dual-output strategy closes.

Every skill generates both:

1. **`SKILL.md`** — Active skill, loaded on trigger with the full instruction set. This is the instruction manual your agent opens when it knows it needs library guidance.
2. **`context-snippet.md`** — Passive context, compressed to 80–120 tokens per skill. Injected into platform context files (`CLAUDE.md` / `AGENTS.md` / `.cursorrules`) only when `export-skill` is run. This is the ambient index that tells your agent the skill exists in the first place and should be opened for relevant work.

Without the snippet, the agent never knows to open `SKILL.md`. Without `SKILL.md`, the snippet has nothing to point at. **Both halves are load-bearing.** That's the 21-point delta.

### Managed Context Section

Export injects a managed section between markers:

The block below is the real managed section currently in [`oh-my-skills/CLAUDE.md`](https://github.com/armelhbobdad/oh-my-skills/blob/main/CLAUDE.md), showing one of its four compiled skills. Every line is verbatim from the file:

```markdown
<!-- SKF:BEGIN updated:2026-04-13 -->
[SKF Skills]|4 skills|0 stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|[oms-cognee v1.0.0]|root: .claude/skills/oms-cognee/
|IMPORTANT: oms-cognee v1.0.0 — read SKILL.md before writing cognee code. Do NOT rely on training data.
|quick-start:SKILL.md#quick-start
|api-v1: add(), cognify(), search(), memify(), update(), run_custom_pipeline(), visualize_graph(), datasets, prune, config, SearchType, pipelines, Drop, run_startup_migrations(), session, tracing
|api-v2: remember()→RememberResult, recall(), improve(), forget(), serve()/disconnect(), visualize(), @agent_memory
|key-types:SKILL.md#key-types — SearchType: GRAPH_COMPLETION (default), RAG_COMPLETION, CHUNKS, CHUNKS_LEXICAL, SUMMARIES, TEMPORAL, CODING_RULES, CYPHER, FEELING_LUCKY, GRAPH_COMPLETION_DECOMPOSITION (+5 more); Task, Drop, RememberResult, DataPoint, 5 Cognee* exceptions
|gotchas: cognee.low_level REMOVED from public API in v1.0.0 (import from cognee.infrastructure.engine directly); cognee.run_migrations REPLACED by cognee.run_startup_migrations (relational + vector); cognee.delete is DEPRECATED since v0.3.9 (use cognee.datasets.delete_data or cognee.forget); cognee.pipelines restructured in v1.0.0 (package with Drop + lazy re-exports); cognee.agent_memory requires async function; cognee.serve() without url triggers Auth0 Device Code Flow; cognee.start_ui is sync and needs pid_callback arg; all add/cognify/search/memify/remember/recall/improve/forget/serve are async — always await.
|
|(three more skills — oms-cocoindex, oms-storybook-react-vite, oms-uitripled — omitted here for brevity; see the full file)
<!-- SKF:END -->
```

~80-120 tokens per skill (version-pinned, retrieval instruction, section anchors, inline gotchas). Root paths are per-IDE — each of the 23 supported IDEs has its own skill directory (e.g., `.claude/skills/`, `.cursor/skills/`, `.github/skills/`, `.windsurf/skills/`). See [`skf-export-skill/assets/managed-section-format.md`](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-export-skill/assets/managed-section-format.md) for the complete IDE → Context File Mapping. Aligned with [Vercel's research](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) finding that indexed format with explicit retrieval instructions dramatically improves agent performance. Developer controls placement. Ferris controls content. Snippet updates only happen at `export-skill` — create and update are draft operations. An `.export-manifest.json` tracks which skills have been explicitly exported, preventing draft skills from leaking into the managed section.

---

## Ownership Model

| Context | `source_authority` | Distribution |
|---------|-------------------|-------------|
| OSS library (maintainer generates) | `official` | `npx skills publish` to agentskills ecosystem |
| Internal service (team generates) | `internal` | `skills/` in repo, ships with code |
| External dependency (consumer generates) | `community` | Local `skills/`, marked as community |

Provenance maps enable verification: an `official` skill's provenance must trace to the actual source repo owned by the author.
