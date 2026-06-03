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
@Ferris campaign status                    — read-only progress summary
```

- **`campaign`** starts a new campaign from stage 0 (Setup). If a `_campaign-state.yaml` already exists, Ferris offers a choice: resume the existing campaign or overwrite with a new one.
- **`campaign resume`** picks up where the last session left off. State is validated on load — if the state file is corrupted, the `.bak` file is used as a fallback.
- **`campaign status`** loads and validates the current state, prints the resume-detection summary plus the tail of the decision log, then stops — no backup, no mutation, no chaining. Use it to check on a long-running campaign without advancing it.
- **`--from=<skill>`** overrides the resume point to the named skill, useful when you want to re-process a specific skill without restarting the entire campaign.

### Override flags

| Flag | Effect |
|------|--------|
| `--headless` / `-H` | Auto-proceed every gate with its default action and emit structured output (see [Headless / Automation](#headless--automation)). |
| `--brief <file>` | Seed targets from a `campaign-brief.yaml` instead of interactive prompts. Implies `--headless`. |
| `--manifest <file>` | Seed targets from a plain-text `name,repo_url,tier,pin` manifest (one per line; trailing `;dep1,dep2` for `depends_on`). Implies `--headless`. |
| `--from=<skill>` | Resume override (see above). |

---

## Stages

Campaign runs through 11 stages (0–10). All stages auto-proceed except Export, which requires explicit approval before writing skills to disk.

| Stage | Name | Description | Auto-proceed |
|-------|------|-------------|--------------|
| 0 | Setup | Initialize campaign state, detect existing skills, and configure output paths | Yes |
| 1 | Strategy | Generate the campaign brief from architecture and dependency analysis | Yes |
| 2 | Pin Validation | Validate version pins for all declared dependencies | Yes |
| 3 | Provenance | Establish provenance records for each target library | Yes |
| 4 | Skill Loop | Drive each Tier A skill through its forge pipeline (AN → BS → CS → TS) in dependency order — export is deferred to the gated Export stage | Yes |
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

- **Tier A** — primary dependencies declared in the architecture. Each gets a full individual pipeline run (AN → BS → CS → TS) during the Skill Loop stage; the tested skills are exported collectively at the gated Export stage.
- **Tier B** — secondary or transitive dependencies. Processed in batch during the Tier B Batch stage with lighter-touch quality requirements.

### Customization

Campaign ships a `customize.toml` workflow surface you can tune without forking the skill. The resolver merges three layers (scalars override, arrays append): the bundled `customize.toml`, then a committed team override at `_bmad/custom/<skill-name>.toml`, then a personal (gitignored) override at `_bmad/custom/<skill-name>.user.toml` — both under {project-root}. What you can set:

- **Quality-gate scalars** — `quality_gate_hard`, `quality_gate_soft_target`, `quality_gate_soft_fallback` (the thresholds above).
- **`campaign_workspace_path`** — relocate the entire campaign workspace (state, backup, brief, archive, decision log) to a shared volume without editing any step file; empty means the default `{forge_data_folder}/_campaign`.
- **`persistent_facts`** — literal sentences or `file:` references (globs supported) injected into every per-skill kickoff, so house style and guardrails reach the whole campaign.
- **Template overrides** — `report_template_path`, `kickoff_template_path`, `brief_template_path` for house-style copies.
- **`on_complete`** — a post-completion hook invoked with `--report-path=<…>` after the report finalizes; hook failures are logged but never fail the campaign.
- **`activation_steps_prepend` / `activation_steps_append`** — org-wide pre-flight or context-load steps around activation.

See the skill's [SKILL.md](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-campaign/SKILL.md) for the full merge contract.

---

## Quality Gates

Campaign enforces two types of quality gates:

The bar is **campaign-wide** — one set of thresholds applied to every skill, not a per-pipeline split:

- **Hard gate** (`zero-critical-high`) — zero critical or high-severity issues allowed. Any skill that fails the hard gate is flagged for manual intervention and blocks the campaign from proceeding past that skill.
- **Soft target** (default 90%) — the score a skill should reach.
- **Soft fallback** (default 80%) — the floor. A skill scoring at or above the fallback but below the target still proceeds; only a skill below the fallback is treated as a soft-gate miss.

All three are tunable via [customization](#customization); the per-campaign brief and any directive `## Quality Overrides` still take precedence at runtime.

---

## Resume

Campaign is designed around the assumption that context will die. File-based state (`_campaign-state.yaml`) survives context death, session timeouts, and machine restarts.

When you resume:

1. Ferris validates the state file against the campaign schema
2. Completed skills are skipped automatically
3. The campaign picks up from the next incomplete skill in dependency order
4. All cross-skill context (dependency graph, quality scores, provenance records) is restored from disk

Use `--from=<skill>` to override the resume point if you need to re-process a specific skill.

### Re-invocation and recovery

- **`campaign` over an existing state** prompts resume-vs-overwrite. Choosing overwrite first archives the existing `_campaign-state.yaml` and `campaign-brief.yaml` to `archive/{name}-{timestamp}/` and logs it to the decision log, so a new campaign never silently clobbers an old one. In headless mode the default is **resume** — archive-and-overwrite happens only when `--brief`/`--manifest` explicitly seeds a new campaign.
- **Corrupt primary, valid `.bak`** — resume auto-recovers by restoring the backup over the primary and logging the recovery; if the backup is also unusable it HALTs (exit 9, `corrupt-state`) reporting both errors.
- **Primary behind the backup** — if the primary looks older than the `.bak` (a possible crash during the last write), Ferris offers `[R]ecover` from the backup or `[K]eep` the primary (the default; headless keeps the primary).

---

## Expected Output

A successful campaign produces:

- **Individual skill packages** — one per dependency, each tested and exported
- **Stack skill(s)** — capstone skills that integrate individual skills into a cohesive project context
- **Campaign report** (`campaign-report.md`) — a post-campaign summary with per-skill quality scores, dependency graph visualization, and overall campaign metrics
- **Headless envelope** (`SKF_CAMPAIGN_RESULT_JSON`) — a structured JSON result for automation consumers

The Export stage (stage 9) is the only non-auto-proceed stage. Ferris presents a summary of all skills to be written and waits for explicit approval before modifying any context files. In headless mode, the write-gate auto-resolves.

---

## Headless / Automation

Campaign is a first-class headless front door for unattended, multi-session production. Add `--headless` / `-H` (or set `headless_mode: true` in preferences); `--brief`/`--manifest` imply it and seed targets non-interactively. In headless mode every confirmation gate auto-proceeds with its default action, each step emits a single-line JSON progress event to **stderr** on entry and exit (`{"stage":N,"name":"<slug>","status":"start|done"}`), and the terminal step emits the `SKF_CAMPAIGN_RESULT_JSON` envelope on stdout.

- **Cancel affordance** — at any interactive gate the operator can type `cancel`, `exit`, or `:q` to leave cleanly; the campaign HALTs with exit code 12 (`user-cancelled`), logs the cancellation, and leaves state intact and resumable. The Export gate is the exception: its own `[C]ancel` exits 11 (`export-cancelled`).
- **Exit codes** — every HARD HALT exits with a stable, documented code so automators branch on the failure class without grepping message text: `0` success, `3` invalid-state, `4` circular-deps, `5` invalid-pin, `6` inaccessible-repo, `7` dependency-deadlock, `8` missing-brief, `9` corrupt-state, `10` report-failure (degraded — the campaign still completes), `11` export-cancelled, `12` user-cancelled.
- **Error envelope** — on any HARD HALT the `SKF_CAMPAIGN_RESULT_JSON` envelope is emitted on stderr in its error variant, carrying `status: "error"`, `exit_code`, the `phase` (step slug), and an `error` object with `code` and `message`.

The full exit-code table and envelope schema live in the skill's [SKILL.md](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-campaign/SKILL.md) under "Exit Codes" and "Result Contract on HARD HALT".

---

## Timing

Campaign duration scales with the number of declared dependencies — each Tier A skill runs a full `AN → BS → CS → TS` pipeline, and Tier B skills run in batch. A campaign is explicitly designed to **span multiple sessions**: file-based state means you can stop after any skill and resume later without losing progress. Factors that affect total time:

- **Skill count and tier mix** — Tier A skills (a full pipeline each) dominate; Tier B batch processing is lighter per skill.
- **Dependency depth** — deep graphs serialize more work (downstream skills wait on upstream APIs); wide, shallow graphs spread more naturally across sessions.
- **Capstone breadth** — stack-skill composition (stage 6) grows with the number of constituent skills.
- **Forge tier** — Deep-tier projects (with QMD and CCC) spend more time per skill on enrichment.

Plan a campaign as multi-session work rather than a single sitting — the resume design above exists precisely so that context death between skills is a non-event.

---

## Related

- [Workflows](../workflows/) — pipeline mode mechanics, headless mode, circuit breakers
- [forge-auto](../forge-auto/) — zero-ceremony single-skill creation (campaign orchestrates many of these)
- [BMAD Synergy](../bmad-synergy/) — how campaign fits into BMAD Phase 3 as an orchestration layer
