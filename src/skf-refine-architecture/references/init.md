---
nextStepFile: 'gap-analysis.md'
refinementRulesData: '{refinementRulesPath}'
# Resolve `{enumerateStackSkillsHelper}` by probing
# `{enumerateStackSkillsProbeOrder}` in order (installed SKF module path
# first, src/ dev-checkout fallback); first existing path wins. §2 calls
# it for the deterministic skill inventory (cascade-resolved exports,
# metadata-hash, confidence-tier mapping).
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Refinement

## STEP GOAL:

Load the architecture document (required), scan the skills folder to build a skill inventory with metadata, load the optional VS feasibility report for context, validate that all inputs exist and meet minimum requirements, and present an initialization summary before auto-proceeding.

## Rules

- Focus only on loading inputs, scanning skills, and validating prerequisites — do not perform analysis
- Present a clear initialization summary so downstream steps have validated inputs

## MANDATORY SEQUENCE

### 1. Accept Input Documents

"**Refine Architecture — Evidence-Backed Refinement** (additive — never deletes original content).

If you wanted to *verify* the stack first, type `cancel` and run `[VS] Verify Stack`; if no skills exist yet, run `[CS] Create Skill`. Otherwise, please provide the following:
1. **Architecture document path** (REQUIRED) — your project's architecture doc to refine
2. **VS feasibility report path** (OPTIONAL) — from a previous [VS] Verify Stack run, for additional context

Or type `cancel` / `exit` / `:q` at any prompt to abort cleanly."

Wait for user input. Store the validated architecture document path as `architecture_doc`. **GATE [default: use args]** — If `{headless_mode}` and `--architecture-doc` was provided: use that path and auto-proceed, log: "headless: using provided architecture path". If `--vs-report-path` was provided, consume it at the VS validation below. If `--architecture-doc` is absent in headless: HALT (exit code 2, `halt_reason: "input-missing"`) and emit the error envelope.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q` at any sub-prompt: Display "Cancelled — no refinement was performed." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**Validate architecture document:**
- Confirm the file exists and is readable
- If missing or unreadable: "Architecture document not found at `{path}`. Provide a valid path."
- HALT (exit code 2, `halt_reason: "input-invalid"`) if the user cannot provide a valid path. In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" immediately.

**Resolve `{arch_project_name}` (names the refined output file):** Read the architecture document's YAML frontmatter. If it declares a `project_name`, store that value as `{arch_project_name}`; otherwise fall back to the config `{project_name}` resolved at activation. Stash `{arch_project_name}` as a workflow-context variable — `compile.md` and `report.md` resolve `{outputFile}` from it. This makes a producer-side refine of a consumer's architecture doc (the producer/consumer forge split) name the proposal after the doc's own project rather than the forge workspace config. Producer-side working state (`ra-state-{project_name}.md`) and the VS report auto-probe stay keyed on the config `{project_name}`.

**Validate VS report (if provided via `--vs-report-path` or interactive input):**
- Confirm the file exists and is readable
- If missing at user-provided path: attempt auto-probe (below) before giving up
- Store VS report availability as `vs_report_available: true|false` and `vs_report_path`

**Scope hint (optional, `--scope-skills`):** If `--scope-skills <names>` was provided, store the parsed comma-separated list as `{scope_skills}` — gap analysis (Step 02 §2b) uses it as the authoritative in-scope skill set. If absent, leave `{scope_skills}` empty; Step 02 derives scope from the architecture document instead.

### 2. Scan Skills Folder

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins.

**Primary path — deterministic enumeration via shared helper:**

```bash
python3 {enumerateStackSkillsHelper} enumerate {skills_output_folder} --pairs --reliability
```

The helper walks `{skills_output_folder}`, reads each `metadata.json`, applies the version-aware resolution (export-manifest → `active` symlink → flat fallback), captures the exports cascade (metadata → references → SKILL.md), maps `confidence_tier`, and emits structured JSON with one entry per skill plus a top-level `warnings[]` array. Cache the result as `skill_inventory`.

`--pairs` additionally attaches `skill_inventory.pairs` — the complete, deterministic set of unique `{library_a, library_b}` combinations over the skill names (`itertools.combinations`, sorted-name order, `pair_count == N*(N-1)/2`) — plus `skill_inventory.pair_count`. Cache both alongside the inventory. This is the exact pair set Step 02 (gap analysis) iterates; the helper owns the combinatorics, so a pair can never be silently dropped or duplicated at larger N and downstream steps read the set rather than re-deriving it.

Each helper-emitted entry includes: `skill_name`, `version`, `language`, `confidence_tier`, `exports_documented`, `source_repo`, `source_root`, and a `metadata_hash` for change-detection across runs. The helper's `warnings[]` carries per-skill skip reasons (missing SKILL.md/metadata.json, non-symlink `active`, orphan-versions, schema-version violations).

**Failure-budget guard:** `--reliability` attaches the helper-computed verdict — `inventory_reliable` (boolean), `unreliable_ratio`, `skill_count`, `warning_count` — so the reliability threshold lives in one unit-tested place and this step reads a boolean rather than re-deriving a ratio. If `inventory_reliable` is false, HALT (exit code 7, `halt_reason: "inventory-unreliable"`) with: "Inventory scan unreliable — {warning_count}/{skill_count + warning_count} skills returned skip warnings. Re-run [RA] after skills stabilize." In headless, emit the error envelope.

**Fallback path — graceful degradation when the helper is unavailable:** If `{enumerateStackSkillsHelper}` has no existing candidate, fall through to the LLM-driven inventory: walk `{skills_output_folder}` and for each `{skill_package}` read `metadata.json` and extract `name`, `language`, `confidence_tier`, `stats.exports_documented`, `source_repo`/`source_root`. Skip packages missing SKILL.md or metadata.json with a logged warning. On this degraded path only — with no helper to consult — treat the run as unreliable and HALT the same way if skip warnings exceed one in five of the scanned packages.

### 3. Validate Minimum Requirements

**Check skill count:**
- At least 1 valid skill must exist
- If no skills found: "**Cannot proceed.** No skills found in `{skills_output_folder}`. Generate skills with [CS] Create Skill or [QS] Quick Skill, then re-run [RA]."
- HALT (exit code 5, `halt_reason: "insufficient-skills"`). In headless, emit the error envelope.
- If exactly 1 valid skill found: "⚠️ Proceeding with 1 skill. Note: gap analysis will find no gaps — pairwise analysis requires at least 2 skills. Step 02 will still execute and issue an appropriate notice. Issue detection and improvement detection will proceed normally."

**Output paths (`{outputFolderPath}`, `forge_data_folder`):** both were asserted non-empty (config-completeness → exit 3, `output-folder-unconfigured` / `forge-folder-unconfigured`) and then probed for writability (→ exit 4, `write-failed`) at On-Activation §5. If either was unconfigured or unwritable the run already halted there, so both are guaranteed present and writable here — no re-check needed.

**Check architecture document:**
- Confirm it was loaded successfully in section 1
- If not: HALT with error (should not reach here if section 1 validation passed)

### 3b. Auto-Probe VS Report

**Auto-probe VS report (if not provided by user in section 1, OR if user-provided path was invalid):**
- Only attempt if `forge_data_folder` is non-empty and the directory exists (validated above); otherwise skip probe and set `vs_report_available: false`
- Check for `{forge_data_folder}/feasibility-report-{project_name}.md`
- If found: "Auto-discovered VS report at `{path}`. Loading for additional context."
- Store `vs_report_available: true` and `vs_report_path`
- If not found: `vs_report_available: false` — "Proceeding without VS report — issue detection will rely on skill data only."

### 3c. Reset RA State File

Create (or overwrite) `{forge_data_folder}/ra-state-{project_name}.md` with a fresh header:

```markdown
<!-- RA state for {project_name} — generated {current_date} -->
```

This ensures steps 02-04 append to a clean slate and context recovery in step 5 never loads stale findings from a prior run.

On any write failure (read-only mount, disk full, permissions denied): HALT (exit code 4, `halt_reason: "write-failed"`) with the captured error and emit the error envelope. The On-Activation §5 probe should have caught this earlier — if it surfaces here, the filesystem state changed mid-workflow.

### 4. Load Refinement Rules

Load `{refinementRulesData}` for reference by downstream steps.

Extract: gap detection rules, issue detection rules, improvement detection rules, citation format, and preservation rules.

### 5. Display Initialization Summary

"**Architecture Refinement Initialized**

| Field | Value |
|-------|-------|
| **Architecture Doc** | {architecture_doc} |
| **VS Report** | {vs_report_path or 'Not provided — issue detection will use skill data only'} |
| **Skills Loaded** | {skill_count} |

**Skill Inventory:**

| Skill | Language | Tier | Exports |
|-------|----------|------|---------|
| {skill_name} | {language} | {confidence_tier} | {exports_documented} |

**Proceeding to gap analysis...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

