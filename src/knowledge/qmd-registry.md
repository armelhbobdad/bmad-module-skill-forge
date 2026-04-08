# QMD Collection Registry

## Principle

QMD collections in the Skill Forge follow a **progressive registry architecture**: workflow steps that produce artifacts index them into QMD collections and register them in `forge-tier.yaml`. Downstream workflow steps discover and query collections through the registry — never by convention or assumption. Collections are created by producers, consumed by searchers, and maintained by a janitor.

## Rationale

Early SKF versions used a blind auto-index strategy: setup would scan all project directories and index them into QMD collections. This created three problems:

- On fresh workspaces, auto-indexing found nothing — wasted work
- Raw source code indexing produced low signal-to-noise search results
- No connection between what was indexed and what workflows actually queried

The progressive registry solves all three by indexing **curated workflow artifacts** (extraction snapshots, skill briefs) instead of raw source files, and only when a workflow produces them.

## Architecture

### Roles

| Role | Workflow | Responsibility |
| --- | --- | --- |
| **Producer** | brief-skill, create-skill | Creates QMD collections from workflow artifacts and registers them in forge-tier.yaml |
| **Consumer** | audit-skill, update-skill, create-stack-skill | Reads the registry, discovers collections by skill name and type, queries via qmd_bridge (see [tool-resolution.md](tool-resolution.md) for concrete resolution) |
| **Janitor** | setup | Cross-references live QMD collections against the registry, cleans orphans and stale entries |

### Registry Schema

The `qmd_collections` array lives in `forge-tier.yaml` alongside tool availability and tier:

```yaml
qmd_collections:
  - name: "my-lib-extraction"
    type: "extraction"
    source_workflow: "create-skill"
    skill_name: "my-lib"
    created_at: "2026-03-14"
  - name: "my-lib-brief"
    type: "brief"
    source_workflow: "brief-skill"
    skill_name: "my-lib"
    created_at: "2026-03-14"
    # status: "pending"    # Optional — see below
```

**Optional field: `status`**

The `status` field is only present when QMD embed verification fails during collection creation. When `status: "pending"` is set, the collection exists in QMD but vector embeddings may be incomplete — only BM25 keyword `search` is reliable. `vector_search` and `deep_search` may return no results until re-embedded. Collections without a `status` field are fully operational. The setup janitor should flag `"pending"` collections for re-embedding.

### Collection Types

| Type | Producer | Content | Primary Consumers |
| --- | --- | --- | --- |
| `extraction` | create-skill step-07 | Compiled SKILL.md, references, context-snippet — structured, confidence-rated exports | audit-skill (drift detection), update-skill (T2 enrichment) |
| `brief` | brief-skill step-05 | skill-brief.yaml — intent, scope, target repository metadata | Portfolio-level search (cross-skill deduplication) |
| `temporal` | create-skill step-03b | GitHub issues, PRs, releases, changelogs — historical and planned context at T2 confidence | step-04 enrichment (temporal annotations per exported function) |
| `docs` | create-skill step-03c | Fetched external documentation — API references, guides, usage examples (T3 confidence) | step-04 enrichment (cross-reference doc context with source-extracted functions) |

### Lifecycle

```
brief-skill writes brief → indexes {name}-brief → registers in forge-tier.yaml
    ↓
create-skill fetches temporal context → indexes {name}-temporal → registers in forge-tier.yaml (Deep only)
    ↓
create-skill fetches docs → indexes {name}-docs → registers in forge-tier.yaml (Deep only)
    ↓
create-skill compiles skill → indexes {name}-extraction → registers in forge-tier.yaml
    ↓
audit-skill reads registry → queries {name}-extraction for drift baseline
update-skill reads registry → queries {name}-extraction for T2 enrichment
    ↓
setup reads registry + QMD state → cleans orphans, removes stale entries
```

## Collection Gate

A new QMD collection type is justified ONLY when:

1. A specific **workflow step** performs a **programmatic search** against it
2. The data is not already accessible through existing artifacts (provenance map, file I/O)
3. QMD search adds value beyond what direct file reading provides

Human readability alone is not sufficient justification — the file is already on disk.

## Rejected Candidates

### Source Clone Indexing

**Proposal:** Clone the target repository and index all source files into QMD.

**Rejection reason:** Freshness problem. A cloned repo is a snapshot pretending to be current. No clear owner for refresh lifecycle. The provenance map already records `file:line` for every export, and ast-grep provides structural queries against local source. QMD indexing of raw source adds noise, not signal.

### Source-Map Indexing

**Proposal:** Index the GitHub API tree response (directory structure + file metadata) as a lightweight `{name}-source-map` collection.

**Rejection reason:** No workflow consumer. Audit-skill already has file paths from provenance-map.json. The source-map would only serve ad-hoc developer queries, which don't justify the collection overhead.

### Analysis Report Indexing

**Proposal:** Index the analyze-source decomposition report as a `{name}-analysis` collection.

**Rejection reason:** Decision artifact, not a compilation input. The analyze-source report tells users which skills to create, but create-stack-skill works from individual skill artifacts, not the analysis report. The only consumer would be a human reading the file — which they can do directly.

## Relationship to CCC Index Registry

The `ccc_index_registry` array in forge-tier.yaml is a **parallel but separate** registry from `qmd_collections`. They track different things:

| Aspect | QMD Collections | CCC Index Registry |
|--------|----------------|-------------------|
| **What is indexed** | Curated workflow artifacts (SKILL.md, briefs, temporal data) | Source code (the actual codebase) |
| **Index engine** | QMD (BM25 + optional vector search) | cocoindex-code (AST + vector embeddings) |
| **Lifecycle** | Per-skill: created by create-skill, consumed by audit/update-skill | Per-project: created by setup, verified by create-skill |
| **Janitor** | setup step-03 (orphan/stale QMD collection cleanup) | setup step-03 section 5b (stale path cleanup) |
| **Availability** | Deep tier only | Forge+ and Deep tiers |

These registries are orthogonal — they never reference each other, and their janitor sections operate independently.

## Pattern Examples

### Example 1: Producer Registration (create-skill)

**Context:** After writing all skill artifacts to disk, create-skill registers them with QMD.

**Implementation:** Deep tier only. Atomic replace if collection exists:

```
qmd collection remove {name}-extraction   (if exists)
qmd collection add {project-root}/skills/{name} --name {name}-extraction --mask "**/*"
qmd embed
```

Then append/replace the registry entry in forge-tier.yaml. Failures never block the workflow. The `qmd embed` call generates vector embeddings required for `vector_search` and `deep_search`.

### Example 2: Consumer Discovery (audit-skill)

**Context:** Audit-skill needs temporal context for drift detection.

**Implementation:** Read `qmd_collections` from forge-tier.yaml. Find entry where `skill_name` matches AND `type` is `"extraction"`. If found, query via qmd_bridge. If not found, log and continue without T2 enrichment — not an error.

### Example 3: Janitor Hygiene (setup)

**Context:** Setup-forge verifies QMD health on every run.

**Implementation:** Cross-reference live QMD collections against registry. Classify as healthy (in both), orphaned (in QMD only), or stale (in registry only). Prompt user before removing orphans. Silently clean stale registry entries.

## Related Fragments

- [progressive-capability.md](progressive-capability.md) — tier model that gates QMD availability to Deep tier
- [skill-lifecycle.md](skill-lifecycle.md) — end-to-end pipeline showing where producers and consumers sit
- [provenance-tracking.md](provenance-tracking.md) — provenance map that provides file:line context without QMD

_Source: progressive QMD registry architecture implemented across setup, brief-skill, create-skill, audit-skill, and update-skill workflows_
