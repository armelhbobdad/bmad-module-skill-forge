---
title: Campaign Orchestration
description: Multi-library skill production with dependency tracking, file-based state, and resume
---

Campaign orchestration drives the production of 15+ coordinated skills through the full SKF pipeline (brief, generate, compile, test, export) in dependency order. It sits at the top of the pipeline ladder — it does not produce skill artifacts directly but sequences the workflows that do.

When your architecture declares many dependencies, running individual pipelines one at a time is tedious and error-prone. Campaign automates the entire loop: it reads the dependency graph, sorts skills topologically, drives each one through the pipeline, enforces quality gates, and tracks state to disk so you can resume after a context death or session break.

---

## Invocation

```
@Ferris campaign                           — start a new campaign
@Ferris campaign resume                    — resume from the last active skill
@Ferris campaign resume --from=<skill>     — resume from a specific skill
```

- **`campaign`** starts a new campaign from stage 0 (Setup). If a `_campaign-state.yaml` already exists, Ferris offers a choice: resume the existing campaign or overwrite with a new one.
- **`campaign resume`** picks up where the last session left off. State is validated on load — if the state file is corrupted, the `.bak` file is used as a fallback.
- **`--from=<skill>`** overrides the resume point to the named skill, useful when you want to re-process a specific skill without restarting the entire campaign.

---

## Stages

Campaign runs through 11 stages (0–10). All stages auto-proceed except Export, which requires explicit approval before writing skills to disk.

| Stage | Name | Description | Auto-proceed |
|-------|------|-------------|--------------|
| 0 | Setup | Initialize campaign state, detect existing skills, and configure output paths | Yes |
| 1 | Strategy | Generate the campaign brief from architecture and dependency analysis | Yes |
| 2 | Pin Validation | Validate version pins for all declared dependencies | Yes |
| 3 | Provenance | Establish provenance records for each target library | Yes |
| 4 | Skill Loop | Drive each Tier A skill through the full pipeline (BS → CS → TS → EX) in dependency order | Yes |
| 5 | Tier B Batch | Process Tier B skills (lower-priority or transitive dependencies) in batch mode | Yes |
| 6 | Capstone | Generate stack skill(s) that integrate individual skills into a cohesive project context | Yes |
| 7 | Verification | Run verification passes across all produced skills for cross-skill consistency | Yes |
| 8 | Refinement | Address gaps found during verification — re-run pipelines for skills that need improvement | Yes |
| 9 | Export | Write all verified skills to disk and update context files — **requires user approval** | No |
| 10 | Maintenance | Generate the campaign report and clean up temporary state | Yes |

---

## Key Concepts

### campaign-brief.yaml

A machine-generated brief that captures the full scope of the campaign: which libraries to skill, their version pins, dependency relationships, and quality targets. Created during the Strategy stage from your architecture document and dependency declarations.

### _campaign-state.yaml

The single source of truth for campaign progress. Every state mutation follows a read-backup-modify-write pattern — the current state is backed up before each write, so a crash during write never loses more than one operation. All progress tracking lives here, not in conversation context.

### _campaign-directive.md

A standing directive document that carries cross-cutting instructions for the campaign. See the [campaign directive spec](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-campaign/references/campaign-directive-spec.md) for the full specification and usage patterns.

### Dependency Tracking

Campaign sorts skills topologically by their dependency graph. If skill B depends on skill A, skill A is produced first. This ensures downstream skills can reference upstream APIs during compilation.

### Tier A vs Tier B

- **Tier A** — primary dependencies declared in the architecture. Each gets a full individual pipeline run (BS → CS → TS → EX) during the Skill Loop stage.
- **Tier B** — secondary or transitive dependencies. Processed in batch during the Tier B Batch stage with lighter-touch quality requirements.

---

## Quality Gates

Campaign enforces two types of quality gates:

- **Hard gate** — zero critical or high-severity issues allowed. Any skill that fails the hard gate is flagged for manual intervention and blocks the campaign from proceeding past that skill.
- **Soft gate** — per-pipeline quality thresholds (e.g., 80% for forge, 90% for deepwiki). Skills that score between the hard floor (60%) and the per-pipeline threshold receive a fallback PASS with an evidence report, and the campaign continues.

---

## Resume

Campaign is designed around the assumption that context will die. File-based state (`_campaign-state.yaml`) survives context death, session timeouts, and machine restarts.

When you resume:

1. Ferris validates the state file against the campaign schema
2. Completed skills are skipped automatically
3. The campaign picks up from the next incomplete skill in dependency order
4. All cross-skill context (dependency graph, quality scores, provenance records) is restored from disk

Use `--from=<skill>` to override the resume point if you need to re-process a specific skill.

---

## Expected Output

A successful campaign produces:

- **Individual skill packages** — one per dependency, each tested and exported
- **Stack skill(s)** — capstone skills that integrate individual skills into a cohesive project context
- **Campaign report** (`campaign-report.md`) — a post-campaign summary with per-skill quality scores, dependency graph visualization, and overall campaign metrics
- **Headless envelope** (`SKF_CAMPAIGN_RESULT_JSON`) — a structured JSON result for automation consumers

The Export stage (stage 9) is the only non-auto-proceed stage. Ferris presents a summary of all skills to be written and waits for explicit approval before modifying any context files. In headless mode, the write-gate auto-resolves.

---

## Timing

Campaign duration scales with the number of declared dependencies — each Tier A skill runs a full `BS → CS → TS → EX` pipeline, and Tier B skills run in batch. A campaign is explicitly designed to **span multiple sessions**: file-based state means you can stop after any skill and resume later without losing progress. Factors that affect total time:

- **Skill count and tier mix** — Tier A skills (a full pipeline each) dominate; Tier B batch processing is lighter per skill.
- **Dependency depth** — deep graphs serialize more work (downstream skills wait on upstream APIs); wide, shallow graphs spread more naturally across sessions.
- **Capstone breadth** — stack-skill composition (stage 6) grows with the number of constituent skills.
- **Forge tier** — Deep-tier projects (with QMD and CCC) spend more time per skill on enrichment.

Plan a campaign as multi-session work rather than a single sitting — the resume design above exists precisely so that context death between skills is a non-event.

---

## Related

- [Workflows](../workflows/) — pipeline mode mechanics, headless mode, circuit breakers
- [deepwiki](../deepwiki/) — zero-ceremony single-skill creation (campaign orchestrates many of these)
- [BMAD Synergy](../bmad-synergy/) — how campaign fits into BMAD Phase 3 as an orchestration layer
