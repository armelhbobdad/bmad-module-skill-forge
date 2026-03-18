---
name: 'step-01-init'
description: 'Load existing skill artifacts, provenance map, and forge tier; detect skill type; present baseline and change scope'

nextStepFile: './step-02-detect-changes.md'
manualSectionRulesFile: '../data/manual-section-rules.md'
---

# Step 1: Initialize Update

## STEP GOAL:

Load the existing skill and all its provenance data, detect whether this is an individual or stack skill, load the forge tier configuration, and present a baseline summary so the user can confirm the update scope before proceeding.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a precision code analyst operating in Surgeon mode
- ✅ Zero-hallucination principle: every statement must trace to actual artifacts
- ✅ Clinical, terse communication — confidence-labeled, AST-backed
- ✅ You bring provenance-driven analysis expertise; the source code provides ground truth

### Step-Specific Rules:

- 🎯 Focus ONLY on loading existing artifacts and establishing the baseline
- 🚫 FORBIDDEN to modify any files in this step — read-only operations
- 🚫 FORBIDDEN to begin change detection — that is step 02
- 💬 Present findings with confidence tier labels on all loaded data

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Load all required artifacts into working context
- 📖 Validate artifact existence before proceeding
- 🚫 FORBIDDEN to proceed without user confirmation at gate

## CONTEXT BOUNDARIES:

- Available: SKF module config (skills_output_folder, forge_data_folder), user-provided skill path
- Focus: artifact loading and baseline establishment
- Limits: read-only — do not modify any files
- Dependencies: setup-forge must have been run (forge-tier.yaml), create-skill or create-stack-skill must have been run (SKILL.md + provenance-map.json)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Request Skill Path

"**Which skill would you like to update?**

Provide either:
- A skill name (resolves to `{skills_output_folder}/{name}/`)
- A full path to the skill folder
- A skill name with `--from-test-report` to use the test report's gap findings instead of source drift detection

**Skill:** {user provides path or name}"

Resolve the path to an absolute skill folder location.

**If `--from-test-report` was provided (or user references a test report):**
Search for the test report at `{forge_data_folder}/{skill_name}/test-report-{skill_name}.md`. If found, set `test_report_path` in context and `update_mode: gap-driven`. If not found, warn and continue with normal source drift mode.

### 2. Validate Required Artifacts

**Check SKILL.md exists:**
- Load `{resolved_skill_path}/SKILL.md`
- If missing: **ABORT** — "No SKILL.md found at `{resolved_skill_path}`. Run create-skill first."

**Check metadata.json exists:**
- Load `{resolved_skill_path}/metadata.json`
- Extract: `name`, `skill_type` (single or stack), `version`, `generation_date`, `confidence_tier`, `source_root`
- If missing: **ABORT** — "No metadata.json found. This skill may have been created manually. Run create-skill to generate provenance data."

**Detect skill type from metadata:**
- If `skill_type == "stack"`: flag as stack skill (multi-file update mode)
- If `skill_type == "single"` or absent: flag as single skill

### 3. Load Forge Tier Configuration

**Load `{sidecar_path}/forge-tier.yaml`:**
- Extract: `tier` (Quick, Forge, or Deep), available tools
- If missing: **ABORT** — "No forge-tier.yaml found. Run setup-forge first to detect available tools."

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, or Deep), use it instead of the detected tier.

**Determine analysis capabilities:**
- **Quick:** text pattern matching only → T1-low confidence
- **Forge:** AST structural extraction → T1 confidence
- **Deep:** AST + QMD semantic enrichment → T1 + T2 confidence

### 4. Load Provenance Map

**Load `{forge_data_folder}/{skill_name}/provenance-map.json`:**
- Extract: export list, file mappings, extraction timestamps, confidence tiers
- Calculate provenance age (days since last extraction)

**If provenance map missing:**

"**WARNING:** No provenance map found at `{forge_data_folder}/{skill_name}/provenance-map.json`.

Without a provenance map, update-skill cannot perform targeted change detection. Options:

**[D]egraded mode** — Perform full re-extraction with T1-low confidence (equivalent to re-running create-skill but preserving [MANUAL] sections)
**[X]** — Abort and run create-skill first to generate provenance data

Select: [D] Degraded / [X] Abort"

- If D: set `degraded_mode = true`, proceed with full extraction scope
- If X: **ABORT**

### 5. Load [MANUAL] Section Inventory

Load {manualSectionRulesFile} to understand [MANUAL] detection patterns.

**Scan SKILL.md for [MANUAL] sections:**
- Count all `<!-- [MANUAL:*] -->` markers
- Map each [MANUAL] block to its parent section (by heading hierarchy)
- Record section names and approximate line positions

**For stack skills, also scan:**
- All `references/*.md` files for [MANUAL] markers
- All `references/integrations/*.md` files for [MANUAL] markers

### 6. Resolve Source Code Path

**From provenance map (if available):**
- Extract `source_root` path
- Validate source path exists and is accessible

**If source path invalid or missing:**

"**Source path from provenance map is invalid:** `{source_root}`

Please provide the current source code path:
**Path:** {user provides path}"

### 7. Present Baseline Summary

"**Update Skill Baseline:**

| Property | Value |
|----------|-------|
| **Skill** | {skill_name} |
| **Type** | {single/stack} |
| **Version** | {version} |
| **Created** | {created date} |
| **Source** | {source_root} |
| **Forge Tier** | {forge_tier} (current) vs {original_tier} (at creation) |
| **Provenance Age** | {days} days since last extraction |
| **Exports** | {export_count} tracked exports |
| **[MANUAL] Sections** | {manual_count} preserved sections |
| **Mode** | {normal/degraded/gap-driven} |

**Analysis plan:** {tier_description}
- {Quick: text pattern diff → T1-low findings}
- {Forge: AST structural diff → T1 findings}
- {Deep: AST structural + QMD semantic diff → T1 + T2 findings}

**Ready to detect changes and update this skill?**"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Change Detection"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C] is selected and baseline has been established with all required artifacts loaded, will you then load and read fully `{nextStepFile}` to execute change detection.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- SKILL.md loaded and validated
- metadata.json loaded with name, skill_type, version, source_root
- Forge tier loaded from sidecar/forge-tier.yaml
- Provenance map loaded (or degraded mode confirmed)
- [MANUAL] sections inventoried across all output files
- Source code path validated
- Baseline summary presented to user
- User confirms scope via [C] Continue

### ❌ SYSTEM FAILURE:

- Not validating artifact existence before proceeding
- Not detecting skill type (individual vs stack)
- Modifying any files during this read-only step
- Proceeding without user confirmation
- Not inventorying [MANUAL] sections before update begins
- Not loading forge tier configuration

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
